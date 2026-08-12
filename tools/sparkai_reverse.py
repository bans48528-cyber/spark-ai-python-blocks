#!/usr/bin/env python3
"""Compile Spark AI generated Python back into a .sparkai project.

This compiler intentionally accepts the Python dialect emitted by Spark AI,
not arbitrary Python.  The project format is Scratch 3 JSON inside a ZIP
archive, so the compiler keeps the assets and target metadata from a fixed
template and replaces only the sprite block graph.
"""

from __future__ import annotations

import ast
import io
import json
import keyword
import re
import tempfile
import tokenize
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PORTS = {letter: index for index, letter in enumerate("ABCDEFGH")}
PORT_LETTERS = {index: letter for letter, index in PORTS.items()}
AUTO_SLEEP = 0.001
VARIABLE_MAPPING_MARKER = "@sparkai-variable"
LIST_MAPPING_MARKER = "@sparkai-list"
SHORT_VARIABLE_MAPPING_MARKER = "@var"
SHORT_LIST_MAPPING_MARKER = "@list"
VARIABLE_MAPPING_MARKERS = (VARIABLE_MAPPING_MARKER, SHORT_VARIABLE_MAPPING_MARKER)
LIST_MAPPING_MARKERS = (LIST_MAPPING_MARKER, SHORT_LIST_MAPPING_MARKER)
CUSTOM_MAPPING_MARKER = "@sparkai-custom"
CUSTOM_ARG_MAPPING_MARKER = "@sparkai-custom-arg"


class ReverseCodeError(ValueError):
    """A user-facing error with a source location."""

    def __init__(self, message: str, node: ast.AST | None = None):
        self.message = message
        self.line = getattr(node, "lineno", None)
        self.column = getattr(node, "col_offset", None)
        location = ""
        if self.line is not None:
            location = f"line {self.line}, column {(self.column or 0) + 1}: "
        super().__init__(location + message)


@dataclass
class MappingReport:
    variables: tuple[tuple[str, str], ...] = ()
    lists: tuple[tuple[str, str], ...] = ()
    unmapped_variables: tuple[str, ...] = ()
    unmapped_lists: tuple[str, ...] = ()


@dataclass
class GeneratedProject:
    path: Path
    block_count: int
    code: str
    mapping_report: MappingReport


@dataclass(frozen=True)
class VariableInfo:
    python_name: str
    display_name: str
    variable_id: str
    initial_value: Any = 0


@dataclass(frozen=True)
class ListInfo:
    python_name: str
    display_name: str
    list_id: str
    initial_items: tuple[Any, ...] = ()


@dataclass(frozen=True)
class CustomArgumentInfo:
    python_name: str
    display_name: str
    kind: str
    argument_id: str
    default: Any = ""


@dataclass(frozen=True)
class CustomInfo:
    python_name: str
    proccode: str
    arguments: tuple[CustomArgumentInfo, ...]
    procedure_id: str


def _custom_argument_kind(token: str) -> str:
    return {"n": "number", "b": "boolean", "s": "string"}[token]


def _custom_argument_opcode(kind: str) -> str:
    return {
        "number": "argument_reporter_number",
        "boolean": "argument_reporter_boolean",
        "string": "argument_reporter_string",
    }[kind]


def _call_path(node: ast.Call) -> str:
    parts: list[str] = []
    current: ast.AST = node.func
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    else:
        raise ReverseCodeError("only named Spark AI functions are supported", node)
    return ".".join(reversed(parts))


def _constant(node: ast.AST, message: str = "a literal value is required") -> Any:
    if isinstance(node, ast.Constant) and node.value is not Ellipsis:
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _constant(node.operand, message)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return -value if isinstance(node.op, ast.USub) else value
    raise ReverseCodeError(message, node)


def _number_text(value: Any, node: ast.AST) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReverseCodeError("a numeric literal is required", node)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _matching_mapping_marker(comment: str, markers: tuple[str, ...]) -> str | None:
    for marker in markers:
        if comment == marker:
            return marker
        if comment.startswith(marker) and len(comment) > len(marker) and comment[len(marker)].isspace():
            return marker
    return None


def _extract_display_mappings(source: str, markers: tuple[str, ...], label: str) -> dict[str, str]:
    """Read explicit Python-name to Spark AI display-name comments."""

    mappings: dict[str, str] = {}
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type != tokenize.COMMENT:
                continue
            comment = token.string[1:].strip()
            marker = _matching_mapping_marker(comment, markers)
            if marker is None:
                continue
            match = re.fullmatch(
                rf"{re.escape(marker)}\s+([^\s=]+)\s*(?:=>|=)\s*(\S.*?)\s*",
                comment,
            )
            if not match:
                aliases = " or ".join(
                    f"# {item} PythonName => DisplayName" if item.startswith("@sparkai-")
                    else f"# {item} PythonName=DisplayName"
                    for item in markers
                )
                raise ReverseCodeError(
                    f"line {token.start[0]}, column {token.start[1] + 1}: "
                    f"invalid {label} mapping comment; use {aliases}"
                )
            python_name, display_name = match.groups()
            if not python_name.isidentifier() or keyword.iskeyword(python_name):
                raise ReverseCodeError(
                    f"line {token.start[0]}, column {token.start[1] + 1}: "
                    f"invalid Python variable name in mapping: {python_name}"
                )
            if python_name in mappings:
                raise ReverseCodeError(
                    f"line {token.start[0]}, column {token.start[1] + 1}: "
                    f"duplicate {label} mapping: {python_name}"
                )
            mappings[python_name] = display_name
    except tokenize.TokenError:
        # ast.parse will provide the authoritative syntax error below.
        pass
    return mappings


def extract_variable_mappings(source: str) -> dict[str, str]:
    return _extract_display_mappings(source, VARIABLE_MAPPING_MARKERS, "variable")


def extract_list_mappings(source: str) -> dict[str, str]:
    return _extract_display_mappings(source, LIST_MAPPING_MARKERS, "list")


def extract_custom_mappings(source: str) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """Read custom-block templates and Python-parameter display mappings."""

    block_mappings: dict[str, str] = {}
    argument_mappings: dict[tuple[str, str], str] = {}
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type != tokenize.COMMENT:
                continue
            comment = token.string[1:].strip()
            if comment.startswith(CUSTOM_ARG_MAPPING_MARKER):
                match = re.fullmatch(
                    rf"{re.escape(CUSTOM_ARG_MAPPING_MARKER)}\s+(\S+)\s+(\S+)\s*=>\s*(\S.*?)\s*",
                    comment,
                )
                if not match:
                    raise ReverseCodeError(
                        f"line {token.start[0]}, column {token.start[1] + 1}: "
                        "invalid custom argument mapping; use "
                        f"# {CUSTOM_ARG_MAPPING_MARKER} FunctionName PythonName => DisplayName"
                    )
                function_name, python_name, display_name = match.groups()
                if (
                    not function_name.isidentifier()
                    or keyword.iskeyword(function_name)
                    or not python_name.isidentifier()
                    or keyword.iskeyword(python_name)
                ):
                    raise ReverseCodeError(
                        f"line {token.start[0]}, column {token.start[1] + 1}: "
                        "custom function and argument names must be Python identifiers"
                    )
                key = (function_name, python_name)
                if key in argument_mappings:
                    raise ReverseCodeError(
                        f"line {token.start[0]}, column {token.start[1] + 1}: "
                        f"duplicate custom argument mapping: {function_name}.{python_name}"
                    )
                argument_mappings[key] = display_name
                continue
            if not comment.startswith(CUSTOM_MAPPING_MARKER):
                continue
            if len(comment) > len(CUSTOM_MAPPING_MARKER) and not comment[len(CUSTOM_MAPPING_MARKER)].isspace():
                continue
            match = re.fullmatch(
                rf"{re.escape(CUSTOM_MAPPING_MARKER)}\s+(\S+)\s*=>\s*(\S.*?)\s*",
                comment,
            )
            if not match:
                raise ReverseCodeError(
                    f"line {token.start[0]}, column {token.start[1] + 1}: "
                    "invalid custom block mapping; use "
                    f"# {CUSTOM_MAPPING_MARKER} FunctionName => BlockTemplate"
                )
            function_name, proccode = match.groups()
            if not function_name.isidentifier() or keyword.iskeyword(function_name):
                raise ReverseCodeError(
                    f"line {token.start[0]}, column {token.start[1] + 1}: "
                    f"invalid custom function name in mapping: {function_name}"
                )
            if function_name in block_mappings:
                raise ReverseCodeError(
                    f"line {token.start[0]}, column {token.start[1] + 1}: "
                    f"duplicate custom block mapping: {function_name}"
                )
            block_mappings[function_name] = proccode
    except tokenize.TokenError:
        pass
    return block_mappings, argument_mappings


def _is_auto_sleep(node: ast.AST) -> bool:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    try:
        if _call_path(node.value) != "_os.sleep_s" or len(node.value.args) != 1:
            return False
        return float(_constant(node.value.args[0])) == AUTO_SLEEP
    except (ReverseCodeError, TypeError, ValueError):
        return False


def _remove_loop_sleep(statements: list[ast.stmt]) -> None:
    """Remove the sleep Spark AI appends to repeat blocks.

    Spark AI's generator appends this line with two Blockly indents.  Depending
    on the last nested branch, Python may parse it as the final statement of
    that branch rather than as a direct loop child, so the final path is
    followed when removing it.
    """

    if not statements:
        return
    last = statements[-1]
    if _is_auto_sleep(last):
        statements.pop()
        return
    if isinstance(last, ast.If):
        branch = last.orelse if last.orelse else last.body
        _remove_loop_sleep(branch)
    elif isinstance(last, (ast.For, ast.While)):
        _remove_loop_sleep(last.body)


def _clean_runtime_sleeps(node: ast.AST) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.For, ast.While)):
            _remove_loop_sleep(child.body)
            _clean_runtime_sleeps(child)
        else:
            _clean_runtime_sleeps(child)


class BlockBuilder:
    """Create Scratch 3 block records with correct parent/input links."""

    def __init__(self) -> None:
        self.blocks: dict[str, dict[str, Any]] = {}
        self.counter = 0

    def new(
        self,
        opcode: str,
        parent: str | None,
        *,
        shadow: bool = False,
        top_level: bool = False,
        x: int | None = None,
        y: int | None = None,
    ) -> str:
        self.counter += 1
        block_id = f"sparkai-{self.counter:04d}"
        block: dict[str, Any] = {
            "opcode": opcode,
            "next": None,
            "parent": parent,
            "inputs": {},
            "fields": {},
            "shadow": shadow,
            "topLevel": top_level,
        }
        if top_level:
            block["x"] = 320 if x is None else x
            block["y"] = 180 if y is None else y
        self.blocks[block_id] = block
        return block_id

    def field(self, block_id: str, name: str, value: Any) -> None:
        self.blocks[block_id]["fields"][name] = [str(value), None]

    def mutation(self, block_id: str, values: dict[str, Any]) -> None:
        self.blocks[block_id]["mutation"] = values

    def input_ref(self, block_id: str, name: str, child_id: str, kind: int = 1) -> None:
        self.blocks[block_id]["inputs"][name] = [kind, child_id]

    def input_ref_with_fallback(
        self,
        block_id: str,
        name: str,
        child_id: str,
        fallback: Any,
        kind: int = 3,
    ) -> None:
        self.blocks[block_id]["inputs"][name] = [kind, child_id, fallback]

    def input_literal(self, block_id: str, name: str, value: Any, literal_type: int = 4) -> None:
        self.blocks[block_id]["inputs"][name] = [1, [literal_type, str(value)]]

    def variable_field(self, block_id: str, name: str, variable: VariableInfo) -> None:
        self.blocks[block_id]["fields"][name] = [variable.display_name, variable.variable_id]

    def list_field(self, block_id: str, name: str, list_info: ListInfo) -> None:
        self.blocks[block_id]["fields"][name] = [list_info.display_name, list_info.list_id]

    def input_variable(
        self,
        block_id: str,
        name: str,
        variable: VariableInfo,
        default: Any = 0,
        *,
        fallback_type: int = 4,
        fallback_opcode: str | None = None,
        top_level: bool = False,
    ) -> str:
        fallback: Any
        shadow = ""
        if fallback_opcode is not None:
            shadow = self.new(
                fallback_opcode,
                None if top_level else block_id,
                shadow=True,
                top_level=top_level,
                x=703,
                y=670,
            )
            self.field(shadow, "NUM", default)
            fallback = shadow
        else:
            fallback = [fallback_type, str(default)]
        self.blocks[block_id]["inputs"][name] = [
            3,
            [12, variable.display_name, variable.variable_id],
            fallback,
        ]
        return shadow

    def link(self, first: str | None, second: str | None) -> None:
        if first and second:
            self.blocks[first]["next"] = second


class SparkAIReverseCompiler:
    """Turn one Spark AI Python script into a sprite block graph."""

    def __init__(self) -> None:
        self.builder = BlockBuilder()
        self.variables: dict[str, VariableInfo] = {}
        self.lists: dict[str, ListInfo] = {}
        self._initialization_nodes: set[int] = set()
        self.variable_mappings: dict[str, str] = {}
        self.list_mappings: dict[str, str] = {}
        self.custom_mappings: dict[str, str] = {}
        self.custom_argument_mappings: dict[tuple[str, str], str] = {}
        self.customs: dict[str, CustomInfo] = {}
        self.custom_nodes: list[ast.FunctionDef] = []
        self.current_custom: CustomInfo | None = None

    def parse(self, source: str) -> ast.Module:
        if not source.strip():
            raise ReverseCodeError("Python input is empty")
        self.variable_mappings = extract_variable_mappings(source)
        self.list_mappings = extract_list_mappings(source)
        self.custom_mappings, self.custom_argument_mappings = extract_custom_mappings(source)
        try:
            tree = ast.parse(source, mode="exec")
        except SyntaxError as exc:
            location = f"line {exc.lineno}, column {exc.offset}: " if exc.lineno else ""
            raise ReverseCodeError(f"Python syntax error: {location}{exc.msg}") from exc
        _clean_runtime_sleeps(tree)
        return tree

    def compile(self, source: str) -> tuple[dict[str, Any], int]:
        tree = self.parse(source)
        self.prepare_variables(tree)
        self.prepare_customs(tree)
        self.builder = BlockBuilder()
        for index, node in enumerate(self.custom_nodes):
            self.custom_definition(node, index)
        event = self.builder.new("event_whenflagclicked", None, top_level=True, x=760, y=180)
        first, _ = self.statement_chain(tree.body, event)
        if first:
            self.builder.link(event, first)
        else:
            raise ReverseCodeError("the program contains no supported statements")
        self.validate_generated_inputs()
        return self.builder.blocks, len(self.builder.blocks)

    def validate_generated_inputs(self) -> None:
        """Reject block graphs whose input shape cannot exist in Spark AI."""

        blocks = self.builder.blocks

        def entry(owner: str, name: str) -> list[Any]:
            value = blocks[owner].get("inputs", {}).get(name)
            if not isinstance(value, list) or len(value) < 2:
                raise ReverseCodeError(
                    f"generated block {blocks[owner].get('opcode')} is missing input {name}"
                )
            return value

        def literal(value: Any, literal_type: int) -> bool:
            return isinstance(value, list) and len(value) >= 2 and value[0] == literal_type

        def plain_number(owner: str, name: str, literal_type: int) -> None:
            value = entry(owner, name)
            nested = value[1]
            if value[0] == 1 and literal(nested, literal_type):
                return
            if value[0] != 3:
                raise ReverseCodeError(
                    f"generated block {blocks[owner].get('opcode')} input {name} "
                    f"does not use a Spark AI numeric value slot"
                )
            if isinstance(nested, list) and len(nested) >= 1 and nested[0] == 12:
                fallback = value[2] if len(value) >= 3 else None
            elif isinstance(nested, str) and nested in blocks:
                child_opcode = blocks[nested].get("opcode")
                if child_opcode in {"motor_box", "combined_motor_box", "sensing_menu"}:
                    raise ReverseCodeError(
                        f"generated block {blocks[owner].get('opcode')} input {name} "
                        f"incorrectly contains a port menu"
                    )
                fallback = value[2] if len(value) >= 3 else None
            else:
                raise ReverseCodeError(
                    f"generated block {blocks[owner].get('opcode')} input {name} "
                    f"has an invalid value reporter"
                )
            if not literal(fallback, literal_type):
                raise ReverseCodeError(
                    f"generated block {blocks[owner].get('opcode')} input {name} "
                    f"is missing its numeric fallback"
                )

        def slider(owner: str, name: str) -> None:
            value = entry(owner, name)
            nested = value[1]
            if value[0] == 1 and isinstance(nested, str) and nested in blocks:
                if blocks[nested].get("opcode") == "math_-100to100_number":
                    return
            if value[0] == 3 and isinstance(nested, str) and nested in blocks:
                fallback = value[2] if len(value) >= 3 else None
                if isinstance(fallback, str) and fallback in blocks:
                    if blocks[fallback].get("opcode") == "math_-100to100_number":
                        return
            if value[0] == 3 and isinstance(nested, list) and len(nested) >= 1 and nested[0] == 12:
                fallback = value[2] if len(value) >= 3 else None
                if isinstance(fallback, str) and fallback in blocks:
                    if blocks[fallback].get("opcode") == "math_-100to100_number":
                        return
            raise ReverseCodeError(
                f"generated block {blocks[owner].get('opcode')} input {name} "
                f"does not use Spark AI's motor slider"
            )

        for block_id, block in blocks.items():
            opcode = block.get("opcode")
            if opcode == "combined_linepatrol_ltr":
                for name in ("PORT_ONE", "PORT_TWO", "LEFT", "RIGHT", "KP", "KD"):
                    plain_number(block_id, name, 4)
            elif opcode == "set_color_threshold_value":
                port = entry(block_id, "PORT")
                if (
                    port[0] != 1
                    or not isinstance(port[1], str)
                    or port[1] not in blocks
                    or blocks[port[1]].get("opcode") != "sensing_menu"
                ):
                    raise ReverseCodeError(
                        "generated color threshold block must use a sensing port menu"
                    )
                plain_number(block_id, "THRESHOLD", 4)
            elif opcode == "matrix_lamp_single":
                for name, expected_opcode in (("x", "matrix_x"), ("y", "matrix_y")):
                    coordinate = entry(block_id, name)
                    if (
                        coordinate[0] != 1
                        or not isinstance(coordinate[1], str)
                        or coordinate[1] not in blocks
                        or blocks[coordinate[1]].get("opcode") != expected_opcode
                    ):
                        raise ReverseCodeError(
                            f"generated matrix block input {name} must use {expected_opcode}"
                        )
            elif opcode == "operator_random":
                plain_number(block_id, "FROM", 4)
                plain_number(block_id, "TO", 4)
            elif opcode == "control_repeat":
                plain_number(block_id, "TIMES", 6)
            elif opcode in {
                "combined_motor_startWithPower",
                "combined_motor_startWithPowerObj",
            }:
                slider(block_id, "POWER_ONE")
                slider(block_id, "POWER_TWO")

    def prepare_customs(self, tree: ast.Module) -> None:
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        function_names = {node.name for node in nodes}
        unknown_mappings = sorted(set(self.custom_mappings) - function_names)
        unknown_argument_mappings = sorted(
            f"{function}.{argument}"
            for function, argument in self.custom_argument_mappings
            if function not in function_names
        )
        if unknown_mappings or unknown_argument_mappings:
            names = ", ".join(unknown_mappings + unknown_argument_mappings)
            raise ReverseCodeError(f"custom mapping refers to unknown function(s): {names}")

        infos: dict[str, CustomInfo] = {}
        proccodes: dict[str, str] = {}
        for index, node in enumerate(nodes, start=1):
            proccode = self.custom_mappings.get(node.name)
            if not proccode:
                raise self.fail(
                    f"missing custom block mapping for {node.name}; add "
                    f"# {CUSTOM_MAPPING_MARKER} {node.name} => BlockTemplate",
                    node,
                )
            if node.decorator_list:
                raise self.fail("custom block definitions cannot have decorators", node)
            if node.args.vararg or node.args.kwarg or node.args.kwonlyargs or node.args.posonlyargs:
                raise self.fail("custom block arguments must be simple positional arguments", node)
            tokens = re.findall(r"%([nbs])", proccode)
            if len(tokens) != len(node.args.args):
                raise self.fail(
                    f"custom block mapping for {node.name} has {len(tokens)} inputs, "
                    f"but the function has {len(node.args.args)} parameters",
                    node,
                )
            if node.name in infos:
                raise self.fail(f"duplicate custom block definition: {node.name}", node)
            previous = proccodes.get(proccode)
            if previous is not None:
                raise self.fail(
                    f"duplicate Spark AI custom block template: {proccode} "
                    f"({previous} and {node.name})",
                    node,
                )
            arguments: list[CustomArgumentInfo] = []
            for argument_index, (argument, token) in enumerate(zip(node.args.args, tokens), start=1):
                display_name = self.custom_argument_mappings.get(
                    (node.name, argument.arg),
                    argument.arg,
                )
                arguments.append(
                    CustomArgumentInfo(
                        python_name=argument.arg,
                        display_name=display_name,
                        kind=_custom_argument_kind(token),
                        argument_id=f"argument-{index:04d}-{argument_index:02d}",
                        default="false" if token == "b" else "",
                    )
                )
            info = CustomInfo(
                python_name=node.name,
                proccode=proccode,
                arguments=tuple(arguments),
                procedure_id=f"procedure-{index:04d}",
            )
            infos[node.name] = info
            proccodes[proccode] = node.name

        for function_name, argument_name in self.custom_argument_mappings:
            info = infos.get(function_name)
            if info is None or argument_name not in {arg.python_name for arg in info.arguments}:
                raise ReverseCodeError(
                    f"custom argument mapping refers to unknown parameter: "
                    f"{function_name}.{argument_name}"
                )
        self.customs = infos
        self.custom_nodes = nodes
        node_ids = {id(node) for node in nodes}
        tree.body = [node for node in tree.body if id(node) not in node_ids]

    def custom_definition(self, node: ast.FunctionDef, index: int) -> str:
        info = self.customs[node.name]
        definition = self.builder.new(
            "procedures_definition",
            None,
            top_level=True,
            x=320,
            y=180 + index * 220,
        )
        prototype = self.builder.new("procedures_prototype", definition, shadow=True)
        self.builder.mutation(
            prototype,
            {
                "tagName": "mutation",
                "children": [],
                "proccode": info.proccode,
                "argumentids": json.dumps(
                    [argument.argument_id for argument in info.arguments],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "argumentnames": json.dumps(
                    [argument.display_name for argument in info.arguments],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "argumentdefaults": json.dumps(
                    [argument.default for argument in info.arguments],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "warp": "false",
            },
        )
        self.builder.input_ref(definition, "custom_block", prototype)
        for argument in info.arguments:
            reporter = self.custom_argument_reporter(prototype, argument, shadow=True)
            self.builder.input_ref(prototype, argument.argument_id, reporter)

        previous = self.current_custom
        self.current_custom = info
        try:
            first, _ = self.statement_chain(node.body, definition)
        finally:
            self.current_custom = previous
        if first:
            self.builder.link(definition, first)
        return definition

    def custom_argument_info(self, node: ast.AST) -> CustomArgumentInfo:
        if self.current_custom is None or not isinstance(node, ast.Name):
            name = node.id if isinstance(node, ast.Name) else "<expression>"
            raise self.fail(f"unknown custom block argument: {name}", node)
        for argument in self.current_custom.arguments:
            if argument.python_name == node.id:
                return argument
        raise self.fail(f"unknown custom block argument: {node.id}", node)

    def custom_argument_reporter(
        self,
        parent: str,
        argument: CustomArgumentInfo,
        *,
        shadow: bool = False,
    ) -> str:
        reporter = self.builder.new(
            _custom_argument_opcode(argument.kind),
            parent,
            shadow=shadow,
        )
        self.builder.field(reporter, "VALUE", argument.display_name)
        return reporter

    def custom_reporter_fallback(
        self,
        owner: str,
        name: str,
        argument: CustomArgumentInfo,
        default: Any,
    ) -> Any:
        block = self.builder.blocks[owner]
        if block.get("opcode") == "matrix_lamp_text":
            return [10, str(default)]
        if block.get("opcode") in {
            "combined_motor_startWithPower",
            "combined_motor_startWithPowerObj",
            "motor_startWithPower",
            "motor_specifiedunit",
        } and name in {"POWER", "POWER_ONE", "POWER_TWO"}:
            shadow = self.builder.new("math_-100to100_number", owner, shadow=True)
            self.builder.field(shadow, "NUM", default)
            return shadow
        if block.get("opcode") == "control_repeat" and name == "TIMES":
            return [6, str(default)]
        if block.get("opcode") == "control_wait" and name == "DURATION":
            return [5, str(default)]
        literal_type = 10 if argument.kind == "string" else 4
        return [literal_type, str(default)]

    def custom_argument_input(
        self,
        owner: str,
        name: str,
        node: ast.Name,
        *,
        kind: int = 1,
        default: Any = 0,
    ) -> str:
        argument = self.custom_argument_info(node)
        if kind == 2:
            if argument.kind != "boolean":
                raise self.fail("only boolean custom arguments can be used as conditions", node)
            reporter = self.custom_argument_reporter(owner, argument)
            self.builder.input_ref(owner, name, reporter, kind=2)
            return reporter
        reporter = self.custom_argument_reporter(owner, argument)
        fallback = self.custom_reporter_fallback(owner, name, argument, default)
        self.builder.input_ref_with_fallback(owner, name, reporter, fallback)
        return reporter

    def custom_call(self, call: ast.Call, parent: str) -> str | None:
        if not isinstance(call.func, ast.Name):
            return None
        info = self.customs.get(call.func.id)
        if info is None:
            return None
        args = self.require_args(call, call.func.id, len(info.arguments))
        block = self.builder.new("procedures_call", parent)
        self.builder.mutation(
            block,
            {
                "tagName": "mutation",
                "children": [],
                "proccode": info.proccode,
                "argumentids": json.dumps(
                    [argument.argument_id for argument in info.arguments],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "warp": "false",
            },
        )
        for argument, value in zip(info.arguments, args):
            if argument.kind == "boolean":
                if isinstance(value, ast.Constant) and isinstance(value.value, bool):
                    raise self.fail("boolean custom arguments must use a boolean block", value)
                self.input_value(block, argument.argument_id, value, kind=2)
            elif argument.kind == "number":
                try:
                    literal = _constant(value)
                except ReverseCodeError:
                    self.input_number(block, argument.argument_id, value)
                else:
                    self.builder.input_literal(block, argument.argument_id, literal, literal_type=4)
            else:
                try:
                    literal = self.string_literal(value)
                except ReverseCodeError:
                    self.input_value(block, argument.argument_id, value)
                else:
                    self.builder.input_literal(block, argument.argument_id, literal, literal_type=10)
        return block

    def prepare_variables(self, tree: ast.Module) -> None:
        global_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.Global)]
        global_names = {
            name
            for node in global_nodes
            for name in node.names
        }
        assignments = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Assign, ast.AugAssign))
        ]

        list_initializers: list[ast.Assign] = []
        list_initializer_names: set[str] = set()
        for node in assignments:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            if not isinstance(node.value, ast.Call):
                continue
            try:
                path = _call_path(node.value)
            except ReverseCodeError:
                continue
            if path != "PikaStdData.List":
                continue
            if node.value.args or node.value.keywords:
                raise self.fail("PikaStdData.List does not accept arguments", node.value)
            name = node.targets[0].id
            if name in list_initializer_names:
                raise self.fail(f"duplicate list initialization: {name}", node)
            list_initializer_names.add(name)
            list_initializers.append(node)

        list_initializer_ids = {id(initializer) for initializer in list_initializers}

        assignment_names: list[str] = []
        assignment_nodes: dict[str, list[ast.Assign | ast.AugAssign]] = {}
        for node in sorted(assignments, key=lambda item: (item.lineno, item.col_offset)):
            target = node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else node.target if isinstance(node, ast.AugAssign) else None
            if not isinstance(target, ast.Name):
                continue
            if id(node) in list_initializer_ids:
                continue
            if target.id not in assignment_nodes:
                assignment_names.append(target.id)
                assignment_nodes[target.id] = []
            assignment_nodes[target.id].append(node)

        names = list(assignment_names)
        for name in sorted(global_names, key=lambda item: next((node.lineno for node in global_nodes if item in node.names), 0)):
            if name not in names and name not in list_initializer_names:
                names.append(name)

        global_line: dict[str, int] = {}
        for node in global_nodes:
            for name in node.names:
                global_line.setdefault(name, node.lineno)

        self._initialization_nodes = set(list_initializer_ids)
        infos: dict[str, VariableInfo] = {}
        for index, name in enumerate(names, start=1):
            initial_value: Any = 0
            candidates = assignment_nodes.get(name, [])
            if name in global_line:
                leading = [node for node in candidates if node.lineno < global_line[name]]
                if leading:
                    initializer = leading[0]
                    if not isinstance(initializer, ast.Assign):
                        raise self.fail("a variable initializer must assign a literal value", initializer)
                    try:
                        initial_value = _constant(initializer.value)
                    except ReverseCodeError as exc:
                        raise self.fail("a variable initializer must assign a literal value", initializer.value) from exc
                    self._initialization_nodes.add(id(initializer))
            infos[name] = VariableInfo(
                python_name=name,
                display_name=name,
                variable_id=f"variable-{index:04d}",
                initial_value=initial_value,
            )
        self.variables = infos

        list_names: dict[str, ListInfo] = {}
        list_display_names: dict[str, str] = {}
        for index, initializer in enumerate(
            sorted(list_initializers, key=lambda item: (item.lineno, item.col_offset)),
            start=1,
        ):
            assert isinstance(initializer.targets[0], ast.Name)
            name = initializer.targets[0].id
            display_name = self.list_mappings.get(name, name)
            previous = list_display_names.get(display_name)
            if previous is not None and previous != name:
                raise ReverseCodeError(
                    f"duplicate Spark AI list display name: {display_name} "
                    f"({previous} and {name})"
                )
            list_display_names[display_name] = name
            list_names[name] = ListInfo(
                python_name=name,
                display_name=display_name,
                list_id=f"list-{index:04d}",
            )
        self.lists = list_names

        unknown_mappings = sorted(set(self.variable_mappings) - set(self.variables))
        if unknown_mappings:
            names = ", ".join(unknown_mappings)
            raise ReverseCodeError(f"variable mapping refers to unknown Python variable(s): {names}")

        display_names: dict[str, str] = {}
        for name, variable in infos.items():
            display_name = self.variable_mappings.get(name, name)
            previous = display_names.get(display_name)
            if previous is not None and previous != name:
                raise ReverseCodeError(
                    f"duplicate Spark AI variable display name: {display_name} "
                    f"({previous} and {name})"
                )
            display_names[display_name] = name
            infos[name] = VariableInfo(
                python_name=variable.python_name,
                display_name=display_name,
                variable_id=variable.variable_id,
                initial_value=variable.initial_value,
            )
        self.variables = infos

        unknown_list_mappings = sorted(set(self.list_mappings) - set(self.lists))
        if unknown_list_mappings:
            names = ", ".join(unknown_list_mappings)
            raise ReverseCodeError(f"list mapping refers to unknown Python list(s): {names}")

        tree.body = [
            node
            for node in tree.body
            if not isinstance(node, ast.Global) and id(node) not in self._initialization_nodes
        ]

    def variable(self, node: ast.AST) -> VariableInfo:
        if not isinstance(node, ast.Name) or node.id not in self.variables:
            name = node.id if isinstance(node, ast.Name) else "<expression>"
            raise self.fail(f"unknown Spark AI variable: {name}", node)
        return self.variables[node.id]

    def variable_input(
        self,
        owner: str,
        name: str,
        node: ast.Name,
        default: Any = 0,
        *,
        fallback_type: int = 4,
        fallback_opcode: str | None = None,
        top_level: bool = False,
    ) -> str:
        variable = self.variable(node)
        return self.builder.input_variable(
            owner,
            name,
            variable,
            default,
            fallback_type=fallback_type,
            fallback_opcode=fallback_opcode,
            top_level=top_level,
        )

    def list_info(self, node: ast.AST) -> ListInfo:
        if not isinstance(node, ast.Name) or node.id not in self.lists:
            name = node.id if isinstance(node, ast.Name) else "<expression>"
            raise self.fail(f"unknown Spark AI list: {name}", node)
        return self.lists[node.id]

    def list_receiver(self, call: ast.Call, method: str) -> ListInfo | None:
        if not isinstance(call.func, ast.Attribute) or call.func.attr != method:
            return None
        if not isinstance(call.func.value, ast.Name):
            raise self.fail("list methods must be called on a named Spark AI list", call)
        return self.list_info(call.func.value)

    def is_list_reporter(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Subscript):
            self.list_info(node.value)
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            return node.func.attr in {"dataToindex", "num", "list_if_data"} and self.list_receiver(node, node.func.attr) is not None
        return False

    def list_reporter_fallback(
        self,
        owner: str,
        name: str,
        default: Any,
        literal_type: int = 4,
    ) -> Any:
        block = self.builder.blocks[owner]
        opcode = block.get("opcode")
        if opcode == "matrix_lamp_text":
            return [10, str(default)]
        if opcode in {
            "combined_motor_startWithPower",
            "combined_motor_startWithPowerObj",
            "motor_startWithPower",
            "motor_specifiedunit",
        } and name in {"POWER", "POWER_ONE", "POWER_TWO"}:
            shadow = self.builder.new("math_-100to100_number", owner, shadow=True)
            self.builder.field(shadow, "NUM", default)
            return shadow
        return [literal_type, str(default)]

    def list_index_node(self, node: ast.Subscript) -> ast.AST:
        index = node.slice
        index_type = getattr(ast, "Index", None)
        if index_type is not None and isinstance(index, index_type):
            index = index.value
        return index

    def list_item_expression(self, node: ast.Subscript, parent: str) -> str:
        block = self.builder.new("data_itemoflist", parent)
        self.builder.list_field(block, "LIST", self.list_info(node.value))
        self.list_index_input(block, "INDEX", self.list_index_node(node))
        return block

    def list_reporter_expression(self, node: ast.Call, parent: str) -> str:
        path = _call_path(node)
        if path.endswith(".dataToindex"):
            list_info = self.list_receiver(node, "dataToindex")
            assert list_info is not None
            args = self.require_args(node, path, 1)
            block = self.builder.new("data_itemnumoflist", parent)
            self.builder.list_field(block, "LIST", list_info)
            self.list_item_input(block, "ITEM", args[0])
            return block
        if path.endswith(".num"):
            list_info = self.list_receiver(node, "num")
            assert list_info is not None
            self.require_args(node, path, 0)
            block = self.builder.new("data_lengthoflist", parent)
            self.builder.list_field(block, "LIST", list_info)
            return block
        if path.endswith(".list_if_data"):
            list_info = self.list_receiver(node, "list_if_data")
            assert list_info is not None
            args = self.require_args(node, path, 1)
            block = self.builder.new("data_listcontainsitem", parent)
            self.builder.list_field(block, "LIST", list_info)
            self.list_item_input(block, "ITEM", args[0])
            return block
        raise self.fail(f"unsupported Spark AI list value function: {path}", node)

    def list_item_input(self, owner: str, name: str, node: ast.AST) -> str:
        try:
            value = _constant(node)
        except ReverseCodeError:
            return self.input_value(owner, name, node)
        self.builder.input_literal(owner, name, value, literal_type=10)
        return ""

    def list_index_input(self, owner: str, name: str, node: ast.AST) -> str:
        try:
            value = _constant(node)
        except ReverseCodeError:
            return self.input_integer(owner, name, node, default=1)
        self.builder.input_literal(owner, name, value, literal_type=7)
        return ""

    def fail(self, message: str, node: ast.AST) -> ReverseCodeError:
        return ReverseCodeError(message, node)

    def require_args(self, node: ast.Call, path: str, count: int) -> list[ast.AST]:
        if node.keywords:
            raise self.fail(f"{path} does not accept keyword arguments", node)
        if len(node.args) != count:
            raise self.fail(f"{path} expects {count} arguments, got {len(node.args)}", node)
        return list(node.args)

    def literal_number(self, node: ast.AST) -> str:
        return _number_text(_constant(node), node)

    def port_index(self, node: ast.AST) -> int:
        value = _constant(node, "a Spark AI port number is required")
        if isinstance(value, str):
            clean = value.strip().upper()
            if clean in PORTS:
                return PORTS[clean]
        if isinstance(value, int) and not isinstance(value, bool) and value in PORT_LETTERS:
            return value
        raise self.fail("port must be A-H or a number from 0 to 7", node)

    def port_menu(self, node: ast.AST, parent: str, *, motor: bool = False) -> str:
        index = self.port_index(node)
        letter = PORT_LETTERS[index]
        opcode = "motor_box" if motor else "sensing_menu"
        child = self.builder.new(opcode, parent, shadow=True)
        self.builder.field(child, "MOTOR" if motor else "SENSING_MENU", letter)
        return child

    def matrix_coordinate_input(self, owner: str, name: str, node: ast.AST, axis: str) -> str:
        value = _constant(node, f"matrix {axis} coordinate must be a literal")
        limit = 9 if axis == "x" else 7
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= limit:
            raise self.fail(
                f"matrix {axis} coordinate must be an integer from 0 to {limit}",
                node,
            )
        opcode = "matrix_x" if axis == "x" else "matrix_y"
        field_name = "X" if axis == "x" else "Y"
        child = self.builder.new(opcode, owner, shadow=True)
        self.builder.field(child, field_name, value)
        self.builder.input_ref(owner, name, child)
        return child

    def motor_pair_menu(self, first: ast.AST, second: ast.AST, parent: str) -> str:
        value = PORT_LETTERS[self.port_index(first)] + "+" + PORT_LETTERS[self.port_index(second)]
        child = self.builder.new("combined_motor_box", parent, shadow=True)
        self.builder.field(child, "MOTOR", value)
        return child

    def matrix_pattern(self, nodes: list[ast.AST], parent: str, call: ast.Call) -> str:
        if len(nodes) != 7:
            raise self.fail("_matrix.show expects 7 five-bit row values", call)
        rows: list[str] = []
        for node in nodes:
            value = _constant(node, "matrix rows must be integer literals")
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0x1F:
                raise self.fail("matrix row values must be integers from 0x00 to 0x1F", node)
            rows.append(format(value, "05b")[::-1])
        block = self.builder.new("matrix_lamp", parent)
        self.builder.field(block, "lamp", "".join(rows))
        return block

    def number_value(self, node: ast.AST, parent: str, *, shadow: bool = True) -> str:
        """Create a generic numeric reporter for an expression-only position."""

        if isinstance(node, ast.Constant) or (
            isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd))
        ):
            child = self.builder.new("math_number", parent, shadow=shadow)
            self.builder.field(child, "NUM", self.literal_number(node))
            return child
        return self.expression_value(node, parent)

    def text_value(self, node: ast.AST, parent: str, *, shadow: bool = True) -> str:
        value = _constant(node, "a text literal is required")
        if not isinstance(value, str):
            raise self.fail("a text literal is required", node)
        child = self.builder.new("text", parent, shadow=shadow)
        self.builder.field(child, "TEXT", value)
        return child

    def input_value(self, owner: str, name: str, node: ast.AST, *, kind: int = 1, default: Any = 0) -> str:
        node = self.unwrap_str(node)
        if isinstance(node, ast.Name):
            if self.current_custom is not None and any(
                argument.python_name == node.id for argument in self.current_custom.arguments
            ):
                return self.custom_argument_input(owner, name, node, kind=kind, default=default)
            return self.variable_input(
                owner,
                name,
                node,
                default,
                fallback_type=10 if isinstance(default, str) else 4,
            )
        try:
            literal = _constant(node)
        except ReverseCodeError:
            literal = None
            is_literal = False
        else:
            is_literal = True
        if is_literal:
            if isinstance(literal, bool):
                if kind != 2:
                    raise self.fail("boolean literals are only supported inside conditions", node)
                self.builder.input_literal(owner, name, literal, literal_type=1)
                return ""
            if isinstance(literal, (int, float)):
                self.builder.input_literal(owner, name, literal, literal_type=4)
                return ""
            if isinstance(literal, str):
                self.builder.input_literal(owner, name, literal, literal_type=10)
                return ""
            raise self.fail("unsupported literal type", node)
        child = self.expression_value(node, owner)
        if self.is_list_reporter(node):
            if kind == 2:
                self.builder.input_ref(owner, name, child, kind=2)
            else:
                fallback = self.list_reporter_fallback(owner, name, default)
                self.builder.input_ref_with_fallback(owner, name, child, fallback)
        elif kind == 2:
            self.builder.input_ref(owner, name, child, kind=2)
        else:
            fallback_type = 10 if isinstance(default, str) else 4
            self.builder.input_ref_with_fallback(
                owner,
                name,
                child,
                [fallback_type, str(default)],
            )
        return child

    def input_number(
        self,
        owner: str,
        name: str,
        node: ast.AST,
        *,
        kind: int = 1,
        default: Any = 0,
        fallback_type: int = 4,
    ) -> str:
        if isinstance(node, ast.Name):
            if self.current_custom is not None and any(
                argument.python_name == node.id for argument in self.current_custom.arguments
            ):
                return self.custom_argument_input(owner, name, node, kind=kind, default=default)
            return self.variable_input(owner, name, node, default, fallback_type=fallback_type)
        try:
            literal = _constant(node)
        except ReverseCodeError:
            pass
        else:
            if isinstance(literal, bool) or not isinstance(literal, (int, float)):
                raise self.fail("a numeric value is required", node)
            self.builder.input_literal(owner, name, literal, literal_type=fallback_type)
            return ""
        child = self.expression_value(node, owner)
        if self.is_list_reporter(node):
            if kind == 2:
                self.builder.input_ref(owner, name, child, kind=2)
            else:
                fallback = self.list_reporter_fallback(owner, name, default, fallback_type)
                self.builder.input_ref_with_fallback(owner, name, child, fallback)
        elif kind == 2:
            self.builder.input_ref(owner, name, child, kind=2)
        else:
            self.builder.input_ref_with_fallback(
                owner,
                name,
                child,
                [fallback_type, str(default)],
            )
        return child

    def input_slider(self, owner: str, name: str, node: ast.AST, *, default: Any = 0) -> str:
        """Serialize slots whose native Spark AI UI is a -100..100 slider."""

        if isinstance(node, ast.Name):
            if self.current_custom is not None and any(
                argument.python_name == node.id for argument in self.current_custom.arguments
            ):
                return self.custom_argument_input(owner, name, node, default=default)
            return self.variable_input(
                owner,
                name,
                node,
                default,
                fallback_opcode="math_-100to100_number",
                top_level=True,
            )
        try:
            literal = _constant(node)
        except ReverseCodeError:
            pass
        else:
            if isinstance(literal, bool) or not isinstance(literal, (int, float)):
                raise self.fail("a numeric value is required", node)
            child = self.builder.new("math_-100to100_number", owner, shadow=True)
            self.builder.field(child, "NUM", literal)
            self.builder.input_ref(owner, name, child)
            return child
        child = self.expression_value(node, owner)
        if self.is_list_reporter(node):
            fallback = self.list_reporter_fallback(owner, name, default, 4)
            self.builder.input_ref_with_fallback(owner, name, child, fallback)
        else:
            fallback = self.builder.new("math_-100to100_number", owner, shadow=True)
            self.builder.field(fallback, "NUM", default)
            self.builder.input_ref_with_fallback(owner, name, child, fallback)
        return child

    def input_positive_number(self, owner: str, name: str, node: ast.AST, *, default: Any = 1) -> str:
        return self.input_number(owner, name, node, default=default, fallback_type=5)

    def input_integer(
        self,
        owner: str,
        name: str,
        node: ast.AST,
        *,
        default: Any = 1,
        literal_type: int = 7,
    ) -> str:
        if isinstance(node, ast.Name):
            if self.current_custom is not None and any(
                argument.python_name == node.id for argument in self.current_custom.arguments
            ):
                return self.custom_argument_input(owner, name, node, default=default)
            return self.variable_input(owner, name, node, default, fallback_type=literal_type)
        try:
            literal = _constant(node)
        except ReverseCodeError:
            pass
        else:
            if isinstance(literal, bool) or not isinstance(literal, int):
                raise self.fail("an integer value is required", node)
            self.builder.input_literal(owner, name, literal, literal_type=literal_type)
            return ""
        child = self.expression_value(node, owner)
        if self.is_list_reporter(node):
            fallback = self.list_reporter_fallback(owner, name, default, literal_type)
        else:
            fallback = [literal_type, str(default)]
        self.builder.input_ref_with_fallback(owner, name, child, fallback)
        return child

    def input_port(self, owner: str, name: str, node: ast.AST, *, motor: bool = False) -> str:
        child = self.port_menu(node, owner, motor=motor)
        self.builder.input_ref(owner, name, child)
        return child

    def input_text(self, owner: str, name: str, node: ast.AST, *, kind: int = 1) -> str:
        return self.input_value(owner, name, node, kind=kind)

    def statement_chain(self, statements: list[ast.stmt], parent: str) -> tuple[str | None, str | None]:
        first: str | None = None
        previous: str | None = None
        for statement in statements:
            if isinstance(statement, ast.Pass) or isinstance(statement, ast.Global) or id(statement) in self._initialization_nodes:
                continue
            block_id = self.statement(statement, parent if previous is None else previous)
            if first is None:
                first = block_id
            if previous is not None:
                self.builder.link(previous, block_id)
            previous = block_id
        return first, previous

    def list_statement(self, call: ast.Call, parent: str) -> str | None:
        if not isinstance(call.func, ast.Attribute):
            return None
        method = call.func.attr
        methods = {
            "append": ("data_addtolist", 1),
            "insert": ("data_insertatlist", 2),
            "set": ("data_replaceitemoflist", 2),
            "remove_index": ("data_deleteoflist", 1),
            "remove_all": ("data_deletealloflist", 0),
        }
        if method not in methods:
            return None
        list_info = self.list_receiver(call, method)
        assert list_info is not None
        opcode, count = methods[method]
        args = self.require_args(call, _call_path(call), count)
        block = self.builder.new(opcode, parent)
        self.builder.list_field(block, "LIST", list_info)
        if method == "append":
            self.list_item_input(block, "ITEM", args[0])
        elif method == "insert":
            self.list_index_input(block, "INDEX", args[0])
            self.list_item_input(block, "ITEM", args[1])
        elif method == "set":
            self.list_index_input(block, "INDEX", args[0])
            self.list_item_input(block, "ITEM", args[1])
        elif method == "remove_index":
            self.list_index_input(block, "INDEX", args[0])
        return block

    def statement(self, node: ast.stmt, parent: str) -> str:
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise self.fail("variable assignment must target one Spark AI variable", node)
            variable = self.variable(node.targets[0])
            block = self.builder.new("data_setvariableto", parent)
            self.builder.variable_field(block, "VARIABLE", variable)
            try:
                literal = _constant(node.value)
            except ReverseCodeError:
                self.input_value(block, "VALUE", node.value)
            else:
                self.builder.input_literal(block, "VALUE", literal, literal_type=10)
            return block
        if isinstance(node, ast.AugAssign):
            if not isinstance(node.target, ast.Name):
                raise self.fail("variable change must target one Spark AI variable", node)
            variable = self.variable(node.target)
            if isinstance(node.op, ast.Add):
                value = node.value
            elif isinstance(node.op, ast.Sub):
                value = ast.UnaryOp(op=ast.USub(), operand=node.value)
                ast.copy_location(value, node.value)
            else:
                raise self.fail("only += or -= variable changes are supported", node)
            block = self.builder.new("data_changevariableby", parent)
            self.builder.variable_field(block, "VARIABLE", variable)
            try:
                literal = _constant(value)
            except ReverseCodeError:
                self.input_value(block, "VALUE", value)
            else:
                self.builder.input_literal(block, "VALUE", literal, literal_type=4)
            return block
        if isinstance(node, ast.If):
            if node.orelse:
                block = self.builder.new("control_if_else", parent)
                condition_name = "CONDITION"
                self.input_value(block, condition_name, node.test, kind=2)
                then_first, _ = self.statement_chain(node.body, block)
                else_first, _ = self.statement_chain(node.orelse, block)
                if then_first:
                    self.builder.input_ref(block, "SUBSTACK", then_first, kind=2)
                if else_first:
                    self.builder.input_ref(block, "SUBSTACK2", else_first, kind=2)
                return block
            block = self.builder.new("control_if", parent)
            self.input_value(block, "CONDITION", node.test, kind=2)
            body_first, _ = self.statement_chain(node.body, block)
            if body_first:
                self.builder.input_ref(block, "SUBSTACK", body_first, kind=2)
            return block
        if isinstance(node, ast.While):
            if isinstance(node.test, ast.Constant) and node.test.value is True:
                block = self.builder.new("control_forever", parent)
            elif isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
                block_opcode = "control_repeat_until" if node.body else "control_wait_until"
                block = self.builder.new(block_opcode, parent)
                self.input_value(block, "CONDITION", node.test.operand, kind=2)
            else:
                raise self.fail("only while True or while not <condition> is supported", node)
            body_first, _ = self.statement_chain(node.body, block)
            if body_first:
                self.builder.input_ref(block, "SUBSTACK", body_first, kind=2)
            return block
        if isinstance(node, ast.For):
            if not isinstance(node.target, ast.Name) or node.target.id != "count":
                raise self.fail("repeat loops must use Spark AI's count variable", node)
            if not isinstance(node.iter, ast.Call) or _call_path(node.iter) != "range":
                raise self.fail("only for count in range(...) is supported", node)
            args = self.require_args(node.iter, "range", 1)
            block = self.builder.new("control_repeat", parent)
            self.input_integer(block, "TIMES", args[0], default=10, literal_type=6)
            body_first, _ = self.statement_chain(node.body, block)
            if body_first:
                self.builder.input_ref(block, "SUBSTACK", body_first, kind=2)
            return block
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            raise self.fail(
                f"unsupported statement {type(node).__name__}; Spark AI generated code must contain hardware calls and control blocks",
                node,
            )
        call = node.value
        path = _call_path(call)

        list_block = self.list_statement(call, parent)
        if list_block is not None:
            return list_block

        custom_block = self.custom_call(call, parent)
        if custom_block is not None:
            return custom_block

        if path == "_motor.pair":
            args = self.require_args(call, path, 3)
            block = self.builder.new("combined_motor_starting", parent)
            ports = self.motor_pair_menu(args[0], args[1], block)
            self.builder.input_ref(block, "PORT", ports)
            self.builder.field(block, "STATUS", self.literal_number(args[2]))
            return block
        if path == "_motor.mov_set_stop_module":
            args = self.require_args(call, path, 1)
            block = self.builder.new("combined_motor_stopping", parent)
            self.builder.field(block, "status", self.literal_number(args[0]))
            return block
        if path == "_motor.mov_power":
            args = self.require_args(call, path, 2)
            block = self.builder.new("combined_motor_startWithPower", parent)
            self.input_slider(block, "POWER_ONE", args[0])
            self.input_slider(block, "POWER_TWO", args[1])
            return block
        if path == "_motor.mov_for_power_seconds":
            args = self.require_args(call, path, 3)
            block = self.builder.new("combined_motor_startWithPowerObj", parent)
            self.input_slider(block, "POWER_ONE", args[0])
            self.input_slider(block, "POWER_TWO", args[1])
            self.input_number(block, "COUNT", args[2], default=1)
            return block
        if path == "_motor.mov_dir_power":
            args = self.require_args(call, path, 2)
            block = self.builder.new("combined_mov_dir_power", parent)
            self.builder.field(block, "DIRECTION", self.string_literal(args[0]))
            self.input_slider(block, "POWER", args[1])
            return block
        if path == "_motor.mov_dir_power_seconds":
            args = self.require_args(call, path, 3)
            block = self.builder.new("combined_mov_dir_power_seconds", parent)
            self.builder.field(block, "DIRECTION", self.string_literal(args[0]))
            self.input_slider(block, "POWER", args[1])
            self.input_slider(block, "SECONDS", args[2], default=1)
            return block
        if path == "_motor.mov_stop":
            self.require_args(call, path, 0)
            return self.builder.new("combined_motor_stop", parent)
        if path == "_motor.mov_find_line_init":
            self.require_args(call, path, 0)
            return self.builder.new("combined_linepatrolInit", parent)
        if path == "_motor.mov_find_line_run":
            args = self.require_args(call, path, 6)
            block = self.builder.new("combined_linepatrol_ltr", parent)
            # The line-patrol block exposes ordinary value inputs. Users can
            # insert numbers, variables, operators, or sensor reporters here.
            self.input_number(block, "PORT_ONE", args[0])
            self.input_number(block, "PORT_TWO", args[1])
            defaults = {"LEFT": 80, "RIGHT": 80, "KP": 0, "KD": 0}
            for name, arg in zip(("LEFT", "RIGHT", "KP", "KD"), args[2:]):
                self.input_number(block, name, arg, default=defaults[name])
            return block
        if path == "_color.set_color_threshold_value":
            args = self.require_args(call, path, 2)
            block = self.builder.new("set_color_threshold_value", parent)
            self.input_port(block, "PORT", args[0])
            self.input_number(block, "THRESHOLD", args[1], default=500)
            return block
        if path == "_motor.mov_set_advance_offset":
            return self.two_number_statement(call, parent, "combined_forward_offset", path, "LEFT_OFFSET", "RIGHT_OFFSET")
        if path == "_motor.mov_set_retreat_offset":
            return self.two_number_statement(call, parent, "combined_backward_offset", path, "LEFT_OFFSET", "RIGHT_OFFSET")
        if path in {"_motor.run_power", "_motor.run_for_power_seconds", "_motor.stop", "_motor.stop_module", "_motor.reset_relative_position"}:
            return self.single_motor_statement(call, parent, path)
        if path == "_os.sleep_s":
            args = self.require_args(call, path, 1)
            block = self.builder.new("control_wait", parent)
            self.input_positive_number(block, "DURATION", args[0], default=1)
            return block
        if path == "_os.stop_exit":
            self.require_args(call, path, 0)
            return self.builder.new("control_stop", parent)
        if path == "_motor.mov_for_degrees":
            args = self.require_args(call, path, 3)
            block = self.builder.new("combined_motor_line", parent)
            direction = self.string_literal(args[0])
            direction_fields = {
                "advance": "Advance",
                "retreat": "Retreat",
                "left": "left",
                "right": "right",
            }
            if direction not in direction_fields:
                raise self.fail(
                    f'{path} direction must be "advance", "retreat", "left", or "right"',
                    args[0],
                )
            unit = self.string_literal(args[2])
            if unit not in {"circly", "angle", "seconds"}:
                raise self.fail(
                    f'{path} unit must be "circly", "angle", or "seconds"',
                    args[2],
                )
            self.builder.field(block, "line", direction_fields[direction])
            self.input_number(block, "distance", args[1])
            self.builder.field(block, "unit", unit)
            return block
        if path in {
            "_matrix.clear",
            "_beep.stop",
            "_os.resetTimer",
            "_mem.restyaw",
        }:
            mapping = {
                "_matrix.clear": "matrix_lamp_stop",
                "_beep.stop": "sound_stopallsounds",
                "_os.resetTimer": "sensing_reset_timer",
                "_mem.restyaw": "sensing_set_yaw_angle",
            }
            self.require_args(call, path, 0)
            return self.builder.new(mapping[path], parent)
        if path == "_matrix.show_roll":
            args = self.require_args(call, path, 1)
            block = self.builder.new("matrix_lamp_text", parent)
            self.input_value(block, "matrix_text", self.unwrap_str(args[0]), default="ABCD")
            return block
        if path == "_matrix.show":
            args = self.require_args(call, path, 7)
            return self.matrix_pattern(args, parent, call)
        if path == "_matrix.set_brightness":
            args = self.require_args(call, path, 1)
            block = self.builder.new("matrix_lamp_set", parent)
            self.builder.field(block, "brightness", self.literal_number(args[0]))
            return block
        if path == "_matrix.set_pixel_brightness":
            args = self.require_args(call, path, 3)
            block = self.builder.new("matrix_lamp_single", parent)
            self.matrix_coordinate_input(block, "x", args[0], "x")
            self.matrix_coordinate_input(block, "y", args[1], "y")
            self.builder.field(block, "switchOnOff", self.literal_number(args[2]))
            return block
        if path == "_beep.play_muic":
            return self.sound_statement(call, parent, path)
        raise self.fail(f"unsupported Spark AI function: {path}", call)

    def input_port_menu(self, owner: str, name: str, node: ast.AST, opcode: str, field_name: str) -> str:
        index = self.port_index(node)
        child = self.builder.new(opcode, owner, shadow=True)
        self.builder.field(child, field_name, PORT_LETTERS[index])
        self.builder.input_ref(owner, name, child)
        return child

    def two_number_statement(self, call: ast.Call, parent: str, opcode: str, path: str, first: str, second: str) -> str:
        args = self.require_args(call, path, 2)
        block = self.builder.new(opcode, parent)
        self.input_number(block, first, args[0])
        self.input_number(block, second, args[1])
        return block

    def single_motor_statement(self, call: ast.Call, parent: str, path: str) -> str:
        count = {"_motor.run_power": 2, "_motor.run_for_power_seconds": 3, "_motor.stop": 1,
                 "_motor.stop_module": 2, "_motor.reset_relative_position": 1}[path]
        args = self.require_args(call, path, count)
        opcode = {
            "_motor.run_power": "motor_startWithPower",
            "_motor.run_for_power_seconds": "motor_specifiedunit",
            "_motor.stop": "motor_stop",
            "_motor.stop_module": "motor_specified_manner",
            "_motor.reset_relative_position": "motor_reset_operating_degree",
        }[path]
        block = self.builder.new(opcode, parent)
        self.input_port(block, "PORT", args[0], motor=True)
        if path == "_motor.run_power":
            self.input_slider(block, "POWER", args[1], default=50)
        elif path == "_motor.run_for_power_seconds":
            self.input_slider(block, "POWER", args[1], default=50)
            self.input_number(block, "COUNT", args[2], default=1)
        elif path == "_motor.stop_module":
            self.builder.field(block, "action", self.literal_number(args[1]))
        return block

    def sound_statement(self, call: ast.Call, parent: str, path: str) -> str:
        if path == "_beep.play_muic":
            args = self.require_args(call, path, 2)
            block = self.builder.new("sound_PlayMusic", parent)
            note = self.string_literal(args[0]).upper()
            child = self.builder.new("piano", block, shadow=True)
            self.builder.field(child, "NOTE", note)
            self.builder.input_ref(block, "NOTE", child)
            self.input_slider(block, "BEATS", args[1], default=0.25)
            return block
        raise self.fail(f"unsupported Spark AI sound function: {path}", call)

    def string_literal(self, node: ast.AST) -> str:
        value = _constant(node, "a string literal is required")
        if not isinstance(value, str):
            raise self.fail("a string literal is required", node)
        return value

    def unwrap_str(self, node: ast.AST) -> ast.AST:
        if isinstance(node, ast.Call) and _call_path(node) == "str":
            args = self.require_args(node, "str", 1)
            return args[0]
        return node

    def expression_value(self, node: ast.AST, parent: str) -> str:
        if isinstance(node, ast.Subscript):
            return self.list_item_expression(node, parent)
        if isinstance(node, ast.Call) and self.is_list_reporter(node):
            return self.list_reporter_expression(node, parent)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return self.number_value(node, parent)
            if isinstance(node.value, str):
                return self.text_value(node, parent)
            if isinstance(node.value, bool):
                raise self.fail("boolean literals are only supported inside conditions", node)
            raise self.fail("unsupported literal type", node)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return self.number_value(node, parent)
        if isinstance(node, ast.BinOp):
            operators = {ast.Add: "operator_add", ast.Sub: "operator_subtract", ast.Mult: "operator_multiply", ast.Div: "operator_divide", ast.Mod: "operator_mod"}
            opcode = next((name for kind, name in operators.items() if isinstance(node.op, kind)), None)
            if opcode is None:
                raise self.fail("unsupported arithmetic operator", node)
            block = self.builder.new(opcode, parent)
            left_name, right_name = (("NUM1", "NUM2") if opcode != "operator_mod" else ("NUM1", "NUM2"))
            self.input_value(block, left_name, node.left)
            self.input_value(block, right_name, node.right)
            return block
        if isinstance(node, ast.BoolOp):
            if len(node.values) != 2:
                raise self.fail("Spark AI logical blocks must have two operands", node)
            opcode = "operator_and" if isinstance(node.op, ast.And) else "operator_or"
            block = self.builder.new(opcode, parent)
            self.input_value(block, "OPERAND1", node.values[0])
            self.input_value(block, "OPERAND2", node.values[1])
            return block
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            block = self.builder.new("operator_not", parent)
            self.input_value(block, "OPERAND", node.operand)
            return block
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise self.fail("chained comparisons are not supported", node)
            if self.is_contains_expression(node):
                block = self.builder.new("operator_contains", parent)
                find_call = node.left
                assert isinstance(find_call, ast.Call)
                assert isinstance(find_call.func, ast.Attribute)
                self.input_value(block, "STRING1", find_call.func.value)
                self.input_value(block, "STRING2", self.find_argument(find_call))
                return block
            opcode = {ast.Gt: "operator_gt", ast.Lt: "operator_lt", ast.Eq: "operator_equals"}.get(type(node.ops[0]))
            if opcode is None:
                raise self.fail("unsupported comparison operator", node)
            block = self.builder.new(opcode, parent)
            self.input_value(block, "OPERAND1", node.left)
            self.input_value(block, "OPERAND2", node.comparators[0])
            return block
        if isinstance(node, ast.Call):
            return self.expression_call(node, parent)
        raise self.fail(f"unsupported expression {type(node).__name__}", node)

    def find_argument(self, node: ast.Call) -> ast.AST:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "find" and len(node.args) == 1:
            return node.args[0]
        raise self.fail("invalid contains expression", node)

    def is_contains_expression(self, node: ast.Compare) -> bool:
        return (
            isinstance(node.left, ast.Call)
            and isinstance(node.left.func, ast.Attribute)
            and node.left.func.attr == "find"
            and len(node.left.args) == 1
            and isinstance(node.ops[0], ast.Gt)
            and _constant(node.comparators[0], "") == -1
        )

    def expression_call(self, node: ast.Call, parent: str) -> str:
        path = _call_path(node)
        sensor_specs = {
            "_color.lux": ("sensing_reflected_light_detection", 1, "PORT"),
            "_color.lux_state": ("sensing_grayscale_state", 1, "PORT"),
            "_color.cmp_lux": ("sensing_reflected_light_judgment", 3, "PORT"),
            "_ultrasion.value": ("sensing_ultrasonic_detection", 1, "PORT"),
            "_ultrasion.cmp_value": ("sensing_ultrasonic_judgment", 3, "PORT"),
            "_touch.state": ("sensing_key_judgment", 1, "PORT"),
        }
        if path == "_key.key_mast":
            args = self.require_args(node, path, 2)
            block = self.builder.new("sensing_mainIsPress", parent)
            self.builder.field(block, "KEYS", self.string_literal(args[0]))
            self.builder.field(block, "BUTTON", self.literal_number(args[1]))
            return block
        if path in sensor_specs:
            opcode, count, _ = sensor_specs[path]
            args = self.require_args(node, path, count)
            block = self.builder.new(opcode, parent)
            self.input_port(block, "PORT", args[0])
            if path in {"_color.cmp_lux", "_ultrasion.cmp_value"}:
                self.builder.field(block, "judgment", self.string_literal(args[1]))
                self.input_number(block, "value", args[2])
            return block
        simple_sensor = {
            "_os.timer": ("sensing_timer", 0),
            "_os.voic": ("sensing_sound_intensity", 0),
            "_math.fmod": ("operator_mod", 2),
            "_math.round": ("operator_round", 1),
        }
        if path in simple_sensor:
            opcode, count = simple_sensor[path]
            args = self.require_args(node, path, count)
            block = self.builder.new(opcode, parent)
            if path == "_math.fmod":
                self.input_value(block, "NUM1", args[0])
                self.input_value(block, "NUM2", args[1])
            elif path == "_math.round":
                self.input_value(block, "NUM", args[0])
            return block
        if path == "str":
            args = self.require_args(node, path, 1)
            return self.expression_value(args[0], parent)
        if path == "len":
            args = self.require_args(node, path, 1)
            block = self.builder.new("operator_length", parent)
            self.input_value(block, "STRING", args[0])
            return block
        if path == "_random.randint":
            args = self.require_args(node, path, 2)
            block = self.builder.new("operator_random", parent)
            self.input_number(block, "FROM", args[0], default=1)
            self.input_number(block, "TO", args[1], default=10)
            return block
        raise self.fail(f"unsupported Spark AI value function: {path}", node)


def load_template(template: Path) -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    try:
        with zipfile.ZipFile(template) as archive:
            entries = [(info.filename, archive.read(info.filename)) for info in archive.infolist() if info.filename != "project.json"]
            project = json.loads(archive.read("project.json").decode("utf-8"))
    except KeyError as exc:
        raise ValueError("template does not contain project.json") from exc
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid .sparkai template: {exc}") from exc
    if not isinstance(project, dict) or not isinstance(project.get("targets"), list):
        raise ValueError("template project.json does not have a targets array")
    if not any(isinstance(target, dict) and not target.get("isStage") for target in project["targets"]):
        raise ValueError("template does not contain a sprite target")
    return project, entries


def mapping_report_from_compiler(compiler: SparkAIReverseCompiler) -> MappingReport:
    return MappingReport(
        variables=tuple(
            (variable.python_name, variable.display_name)
            for variable in compiler.variables.values()
            if variable.python_name in compiler.variable_mappings
        ),
        lists=tuple(
            (list_info.python_name, list_info.display_name)
            for list_info in compiler.lists.values()
            if list_info.python_name in compiler.list_mappings
        ),
        unmapped_variables=tuple(
            variable.python_name
            for variable in compiler.variables.values()
            if variable.python_name not in compiler.variable_mappings
        ),
        unmapped_lists=tuple(
            list_info.python_name
            for list_info in compiler.lists.values()
            if list_info.python_name not in compiler.list_mappings
        ),
    )


def compile_project(source: str, template: Path, output: Path) -> GeneratedProject:
    template = template.resolve()
    output = output.resolve()
    if template == output:
        raise ValueError("output path must not be the fixed template path")
    compiler = SparkAIReverseCompiler()
    blocks, block_count = compiler.compile(source)
    project, entries = load_template(template)
    stage = next(
        (target for target in project["targets"] if isinstance(target, dict) and target.get("isStage")),
        None,
    )
    if stage is None:
        raise ValueError("template does not contain a stage target")
    sprite = next(target for target in project["targets"] if isinstance(target, dict) and not target.get("isStage"))
    sprite["blocks"] = blocks
    stage["variables"] = {
        variable.variable_id: [variable.display_name, variable.initial_value]
        for variable in compiler.variables.values()
    }
    stage["lists"] = {
        list_info.list_id: [list_info.display_name, list(list_info.initial_items)]
        for list_info in compiler.lists.values()
    }
    mapping_report = mapping_report_from_compiler(compiler)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="sparkai-", suffix=".sparkai", dir=output.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in entries:
                archive.writestr(name, content)
            archive.writestr("project.json", json.dumps(project, ensure_ascii=False, separators=(",", ":")))
        output.unlink(missing_ok=True)
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return GeneratedProject(
        path=output,
        block_count=block_count,
        code=source,
        mapping_report=mapping_report,
    )


def default_output_name() -> str:
    return "generated-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".sparkai"


def unique_output_path(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / default_output_name()
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 1
    while True:
        candidate = directory / f"{stem}-{index:02d}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def main(argv: Iterable[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Python file, or - to read Python from stdin")
    default_template = Path(__file__).resolve().parents[1] / "templates" / "base.sparkai"
    parser.add_argument("--template", default=str(default_template))
    parser.add_argument("--output", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        source = sys.stdin.read() if args.source == "-" else Path(args.source).read_text(encoding="utf-8")
        output = Path(args.output) if args.output else unique_output_path(Path("generated"))
        result = compile_project(source, Path(args.template), output)
        print(f"Generated: {result.path}")
        print(f"Blocks: {result.block_count}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
