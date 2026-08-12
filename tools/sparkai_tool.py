#!/usr/bin/env python3
"""Inspect Spark-AI projects and compare generated Python with a reference file.

The project format is a Scratch 3 style ZIP archive.  This MVP deliberately
supports a small, explicit opcode registry so unsupported blocks are visible
instead of being silently guessed.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import keyword
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    from .sparkai_reverse import (
        REMOTE_AXES,
        REMOTE_BUTTON_STATES,
        _clean_runtime_sleeps,
        compile_project,
        project_extensions_for_blocks,
        unique_output_path,
    )
except ImportError:
    from sparkai_reverse import (
        REMOTE_AXES,
        REMOTE_BUTTON_STATES,
        _clean_runtime_sleeps,
        compile_project,
        project_extensions_for_blocks,
        unique_output_path,
    )


PORTS = {letter: index for index, letter in enumerate("ABCDEFGH")}


class ProjectFormatError(ValueError):
    pass


@dataclass
class ProjectData:
    path: Path
    data: dict[str, Any]
    entries: list[str]


@dataclass
class GeneratorResult:
    code: str
    unsupported: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CustomProcedure:
    proccode: str
    function_name: str
    argument_ids: tuple[str, ...]
    display_argument_names: tuple[str, ...]
    argument_names: tuple[str, ...]
    argument_kinds: tuple[str, ...]
    definition_id: str


def load_project(path: Path) -> ProjectData:
    with zipfile.ZipFile(path) as archive:
        try:
            project = json.loads(archive.read("project.json").decode("utf-8"))
        except KeyError as exc:
            raise ProjectFormatError("archive does not contain project.json") from exc
        except UnicodeDecodeError as exc:
            raise ProjectFormatError("project.json is not UTF-8") from exc
        except json.JSONDecodeError as exc:
            raise ProjectFormatError(f"project.json is invalid JSON: {exc}") from exc
        entries = archive.namelist()

    if not isinstance(project, dict) or not isinstance(project.get("targets"), list):
        raise ProjectFormatError("project.json does not have a targets array")
    return ProjectData(path=path, data=project, entries=entries)


def sprite_targets(project: ProjectData) -> list[dict[str, Any]]:
    return [
        target
        for target in project.data["targets"]
        if isinstance(target, dict) and not target.get("isStage", False)
    ]


def stage_variables(project: ProjectData) -> dict[str, Any]:
    for target in project.data["targets"]:
        if isinstance(target, dict) and target.get("isStage", False):
            variables = target.get("variables", {})
            return variables if isinstance(variables, dict) else {}
    return {}


def stage_lists(project: ProjectData) -> dict[str, Any]:
    for target in project.data["targets"]:
        if isinstance(target, dict) and target.get("isStage", False):
            lists = target.get("lists", {})
            return lists if isinstance(lists, dict) else {}
    return {}


def get_blocks(target: dict[str, Any]) -> dict[str, dict[str, Any]]:
    blocks = target.get("blocks", {})
    if not isinstance(blocks, dict):
        raise ProjectFormatError(f"target {target.get('name', '<unnamed>')} has invalid blocks")
    return blocks


def field(block: dict[str, Any], name: str, default: str = "") -> str:
    value = block.get("fields", {}).get(name, [default, None])
    if isinstance(value, list) and value:
        return str(value[0])
    return default


def strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def numeric_or_string(value: Any) -> str:
    text = str(value)
    if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", text):
        return text
    return quote(text)


def matrix_rows_to_hex(pattern: str) -> str:
    rows = [pattern[index:index + 5] for index in range(0, len(pattern), 5)]
    values = []
    for row in rows:
        padded = row.ljust(5, "0")[:5]
        values.append(f"0x{int(padded[::-1], 2):02X}")
    return ",".join(values)


class PythonGenerator:
    """A deterministic subset of the Spark-AI Python generators."""

    def __init__(
        self,
        target: dict[str, Any],
        variables: dict[str, Any] | None = None,
        lists: dict[str, Any] | None = None,
    ):
        self.target = target
        self.blocks = get_blocks(target)
        self.variable_names = {
            str(variable_id): str(value[0])
            for variable_id, value in (variables or {}).items()
            if isinstance(value, list) and value
        }
        self.list_names = {
            str(list_id): str(value[0])
            for list_id, value in (lists or {}).items()
            if isinstance(value, list) and value
        }
        self.unsupported: list[dict[str, str]] = []
        self.warnings: list[str] = []
        self._active: set[str] = set()
        self.custom_procedures: dict[str, CustomProcedure] = {}
        self.current_custom: CustomProcedure | None = None

    def record_unsupported(self, block_id: str, block: dict[str, Any]) -> None:
        item = {"id": block_id, "opcode": str(block.get("opcode", ""))}
        if item not in self.unsupported:
            self.unsupported.append(item)

    def mutation_array(self, block: dict[str, Any], name: str) -> list[str]:
        mutation = block.get("mutation")
        value = mutation.get(name) if isinstance(mutation, dict) else None
        if not isinstance(value, str):
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed]

    def safe_argument_names(self, names: list[str]) -> tuple[str, ...]:
        result: list[str] = []
        used: set[str] = set()
        for index, name in enumerate(names):
            candidate = name if name.isidentifier() and not keyword.iskeyword(name) else f"arg{index}"
            if candidate in used:
                candidate = f"{candidate}_{index}"
            used.add(candidate)
            result.append(candidate)
        return tuple(result)

    def collect_custom_procedures(self) -> list[CustomProcedure]:
        definitions = [
            (block_id, block)
            for block_id, block in self.blocks.items()
            if block.get("opcode") == "procedures_definition"
            and block.get("topLevel")
            and not block.get("shadow")
        ]
        definitions.sort(key=lambda item: (item[1].get("y", 0), item[1].get("x", 0)))
        procedures: list[CustomProcedure] = []
        for index, (definition_id, definition) in enumerate(definitions):
            prototype_id = self.input_block_id(definition, "custom_block")
            prototype = self.blocks.get(prototype_id) if prototype_id else None
            mutation = prototype if isinstance(prototype, dict) else definition
            proccode = str(mutation.get("mutation", {}).get("proccode", ""))
            argument_ids = self.mutation_array(mutation, "argumentids")
            argument_names = self.mutation_array(mutation, "argumentnames")
            kinds = [kind for kind in re.findall(r"%([nbs])", proccode)]
            if not proccode or len(argument_ids) != len(kinds) or len(argument_names) != len(kinds):
                self.warnings.append(f"invalid custom procedure metadata: {definition_id}")
                self.record_unsupported(definition_id, definition)
                continue
            procedure = CustomProcedure(
                proccode=proccode,
                function_name=f"customFunc{index}",
                argument_ids=tuple(argument_ids),
                display_argument_names=tuple(argument_names),
                argument_names=self.safe_argument_names(argument_names),
                argument_kinds=tuple(kinds),
                definition_id=definition_id,
            )
            procedures.append(procedure)
        self.custom_procedures = {procedure.proccode: procedure for procedure in procedures}
        return procedures

    def argument_reporter_code(self, block: dict[str, Any]) -> str:
        display_name = field(block, "VALUE", "")
        if self.current_custom is None:
            return display_name
        for display, python_name in zip(
            self.current_custom.display_argument_names,
            self.current_custom.argument_names,
        ):
            if display == display_name:
                return python_name
        return display_name

    def custom_call_code(self, block: dict[str, Any]) -> str:
        mutation = block.get("mutation", {})
        proccode = str(mutation.get("proccode", "")) if isinstance(mutation, dict) else ""
        procedure = self.custom_procedures.get(proccode)
        if procedure is None:
            return f"<unsupported:procedures_call>"
        values = []
        for argument_id, kind in zip(procedure.argument_ids, procedure.argument_kinds):
            values.append(self.input_value(block, argument_id, "False" if kind == "b" else "0"))
        return f"{procedure.function_name}({', '.join(values)})"

    def custom_definition_lines(self, procedure: CustomProcedure) -> list[str]:
        definition = self.blocks[procedure.definition_id]
        previous = self.current_custom
        self.current_custom = procedure
        try:
            lines = [
                f"def {procedure.function_name}({', '.join(procedure.argument_names)}):"
            ]
            global_names = list(dict.fromkeys(self.variable_names.values()))
            if global_names:
                lines.append(f"  global {', '.join(global_names)}")
            body = self.emit_chain(definition.get("next"), 1)
            lines.extend(body or ["  pass"])
            return lines
        finally:
            self.current_custom = previous

    def port_number(self, value: str) -> str:
        clean = strip_quotes(value).strip()
        if "+" in clean:
            parts = [PORTS.get(item.strip(), item.strip()) for item in clean.split("+")]
            return ",".join(str(item) for item in parts)
        return str(PORTS.get(clean, clean))

    def input_value(self, block: dict[str, Any], name: str, default: str = "0") -> str:
        entry = block.get("inputs", {}).get(name)
        if entry is None:
            return default
        if not isinstance(entry, list) or len(entry) < 2:
            return default

        value = entry[1]
        if isinstance(value, list) and len(value) >= 2:
            if value[0] == 12 and len(value) >= 3:
                return self.variable_names.get(str(value[2]), str(value[1]))
            return numeric_or_string(value[1])
        if isinstance(value, str) and value in self.blocks:
            return self.value_code(value)
        if len(entry) >= 3 and isinstance(entry[2], str) and entry[2] in self.blocks:
            return self.value_code(entry[2])
        return numeric_or_string(value)

    def variable_from_field(self, block: dict[str, Any], name: str = "VARIABLE") -> str:
        value = block.get("fields", {}).get(name, ["", None])
        if isinstance(value, list) and value:
            variable_id = value[1] if len(value) > 1 else None
            if variable_id is not None:
                return self.variable_names.get(str(variable_id), str(value[0]))
            return str(value[0])
        return ""

    def list_from_field(self, block: dict[str, Any], name: str = "LIST") -> str:
        value = block.get("fields", {}).get(name, ["", None])
        if isinstance(value, list) and value:
            list_id = value[1] if len(value) > 1 else None
            if list_id is not None:
                return self.list_names.get(str(list_id), str(value[0]))
            return str(value[0])
        return ""

    def list_item_input(self, block: dict[str, Any], name: str = "ITEM") -> str:
        entry = block.get("inputs", {}).get(name)
        if not isinstance(entry, list) or len(entry) < 2:
            return ""
        value = entry[1]
        if isinstance(value, list) and len(value) >= 2:
            if value[0] == 12 and len(value) >= 3:
                return self.variable_names.get(str(value[2]), str(value[1]))
            return quote(str(value[1]))
        if isinstance(value, str) and value in self.blocks:
            return self.value_code(value)
        return quote(str(value))

    def input_block_id(self, block: dict[str, Any], name: str) -> str | None:
        entry = block.get("inputs", {}).get(name)
        if not isinstance(entry, list):
            return None
        for item in entry[1:]:
            if isinstance(item, str) and item in self.blocks:
                return item
        return None

    def port_input(self, block: dict[str, Any], name: str) -> str:
        return self.port_number(self.input_value(block, name, "0"))

    def value_code(self, block_id: str) -> str:
        block = self.blocks[block_id]
        opcode = block.get("opcode", "")

        if opcode in {
            "math_number",
            "math_integer",
            "math_whole_number",
            "math_positive_number",
            "math_-100to100_number",
        }:
            return numeric_or_string(field(block, "NUM", "0"))
        if opcode == "text":
            return quote(field(block, "TEXT", ""))
        if opcode == "note":
            return field(block, "NOTE", "60")
        if opcode == "piano":
            return field(block, "NOTE", "C")
        if opcode == "data_variable":
            return self.variable_from_field(block)
        if opcode in {
            "argument_reporter_number",
            "argument_reporter_boolean",
            "argument_reporter_string",
        }:
            return self.argument_reporter_code(block)
        if opcode == "data_itemoflist":
            list_name = self.list_from_field(block)
            index = self.input_value(block, "INDEX", "1")
            return f"{list_name}[{index}]"
        if opcode == "data_itemnumoflist":
            list_name = self.list_from_field(block)
            item = self.list_item_input(block)
            return f"{list_name}.dataToindex({item})"
        if opcode == "data_lengthoflist":
            return f"{self.list_from_field(block)}.num()"
        if opcode == "data_listcontainsitem":
            list_name = self.list_from_field(block)
            item = self.list_item_input(block)
            return f"{list_name}.list_if_data({item})"
        if opcode == "combined_motor_box":
            return self.port_number(field(block, "MOTOR", "E+F"))
        if opcode == "combined_motorOne_menu":
            return field(block, "COMBINED_MOTORONE_MENU", "A")
        if opcode == "combined_motorTwo_menu":
            return field(block, "COMBINED_MOTORTWO_MENU", "B")
        if opcode == "motor_box":
            return self.port_number(field(block, "MOTOR", "A"))
        if opcode in {"motor_port", "motor_linepatrol"}:
            return quote(field(block, "MOTOR", "A"))
        if opcode == "sound_sounds_menu":
            return field(block, "SOUND_MENU", "0")
        if opcode in {"sensing_menu", "touching_menu", "handShank_menu"}:
            name = {
                "sensing_menu": "SENSING_MENU",
                "touching_menu": "TOUCHING_MENU",
                "handShank_menu": "HAND_SHANK",
            }[opcode]
            return quote(field(block, name))
        if opcode == "matrix_x":
            return field(block, "X", "0")
        if opcode == "matrix_y":
            return field(block, "Y", "0")
        if opcode == "matrix":
            return field(block, "MATRIX", "0")
        if opcode == "sensing_reflected_light_detection":
            return f"_color.lux({self.port_input(block, 'PORT')})"
        if opcode == "sensing_grayscale_state":
            return f"_color.lux_state({self.port_input(block, 'PORT')})"
        if opcode == "sensing_reflected_light_judgment":
            port = self.port_input(block, "PORT")
            judgment = field(block, "judgment", ">")
            value = self.input_value(block, "value", "0")
            return f'_color.cmp_lux({port}, "{judgment}", {value})'
        if opcode == "sensing_ultrasonic_detection":
            return f"_ultrasion.value({self.port_input(block, 'PORT')})"
        if opcode == "sensing_ultrasonic_judgment":
            port = self.port_input(block, "PORT")
            judgment = field(block, "judgment", ">")
            value = self.input_value(block, "value", "0")
            return f'_ultrasion.cmp_value({port}, "{judgment}", {value})'
        if opcode == "sensing_key_judgment":
            return f"_touch.state({self.port_input(block, 'PORT')})"
        if opcode == "sensing_mainIsPress":
            keys = field(block, "KEYS", "left")
            button = field(block, "BUTTON", "1")
            return f'_key.key_mast("{keys}", {button})'
        if opcode == "sensing_isHandling":
            button = self.input_value(block, "PORT", '"up"').strip('"\'')
            state = field(block, "BUTTON", "press")
            return f'_key.key_remote("{button}", "{state}")'
        if opcode == "sensing_Handling":
            rocker = field(block, "KEYS", "left")
            axis = field(block, "BUTTON", "x")
            return f'_key.key_remote("{rocker}", "{axis}")'
        if opcode == "sensing_timer":
            return "_os.timer()"
        if opcode == "sensing_sound_intensity":
            return "_os.voic()"
        if opcode == "operator_add":
            return self.operator_binary(block, " + ")
        if opcode == "operator_subtract":
            return self.operator_binary(block, " - ")
        if opcode == "operator_multiply":
            return self.operator_binary(block, " * ")
        if opcode == "operator_divide":
            return self.operator_binary(block, " / ")
        if opcode == "operator_gt":
            return self.operator_binary(block, " > ")
        if opcode == "operator_lt":
            return self.operator_binary(block, " < ")
        if opcode == "operator_equals":
            return self.operator_binary(block, " == ")
        if opcode == "operator_and":
            return self.operator_binary(block, " and ")
        if opcode == "operator_or":
            return self.operator_binary(block, " or ")
        if opcode == "operator_not":
            return "not " + self.input_value(block, "OPERAND", "false")
        if opcode == "operator_mod":
            return f"_math.fmod({self.input_value(block, 'NUM1')}, {self.input_value(block, 'NUM2')})"
        if opcode == "operator_round":
            return f"_math.round({self.input_value(block, 'NUM')})"
        if opcode == "operator_random":
            return f"_random.randint({self.input_value(block, 'FROM')}, {self.input_value(block, 'TO')})"
        if opcode == "operator_join":
            left = self.input_value(block, "STRING1", "''")
            right = self.input_value(block, "STRING2", "''")
            return f"str({left}) + str({right})"
        if opcode == "operator_length":
            value = self.input_value(block, "STRING", "''")
            return f"len({value})"
        if opcode == "operator_contains":
            left = self.input_value(block, "STRING1", "''")
            right = self.input_value(block, "STRING2", "0")
            return f"str({left}).find(str({right})) > -1"

        self.record_unsupported(block_id, block)
        return f"<unsupported:{opcode}>"

    def operator_binary(self, block: dict[str, Any], operator: str) -> str:
        left = self.input_value(block, "NUM1", self.input_value(block, "OPERAND1", "0"))
        right = self.input_value(block, "NUM2", self.input_value(block, "OPERAND2", "0"))
        return left + operator + right

    def condition_code(self, owner: dict[str, Any] | str | None, name: str = "CONDITION") -> str:
        if isinstance(owner, dict):
            entry = owner.get("inputs", {}).get(name)
            if isinstance(entry, list) and len(entry) >= 2:
                value = entry[1]
                if isinstance(value, list) and len(value) >= 3 and value[0] == 12:
                    return self.variable_names.get(str(value[2]), str(value[1]))
            block_id = self.input_block_id(owner, name)
        else:
            block_id = owner
        if not block_id:
            return "False"
        block = self.blocks[block_id]
        opcode = block.get("opcode", "")
        if opcode == "sensing_reflected_light_judgment":
            port = self.port_input(block, "PORT")
            judgment = field(block, "judgment", ">")
            value = self.input_value(block, "value", "0")
            return f'_color.cmp_lux({port}, "{judgment}", {value})'
        if opcode == "sensing_ultrasonic_judgment":
            port = self.port_input(block, "PORT")
            judgment = field(block, "judgment", ">")
            value = self.input_value(block, "value", "0")
            return f'_ultrasion.cmp_value({port}, "{judgment}", {value})'
        if opcode == "sensing_key_judgment":
            return f"_touch.state({self.port_input(block, 'PORT')})"
        if opcode == "sensing_mainIsPress":
            keys = field(block, "KEYS", "left")
            button = field(block, "BUTTON", "1")
            return f'_key.key_mast("{keys}", {button})'
        if opcode == "sensing_isHandling":
            button = self.input_value(block, "PORT", '"up"').strip('"\'')
            state = field(block, "BUTTON", "press")
            if state in REMOTE_BUTTON_STATES:
                return f'_key.key_remote("{button}", "{state}")'
        if opcode == "sensing_Handling":
            rocker = field(block, "KEYS", "left")
            axis = field(block, "BUTTON", "x")
            if axis in REMOTE_AXES:
                return f'_key.key_remote("{rocker}", "{axis}")'
        if opcode in {"operator_gt", "operator_lt", "operator_equals", "operator_and", "operator_or", "operator_not"}:
            return self.value_code(block_id)
        return self.value_code(block_id)

    def emit_chain(self, start_id: str | None, level: int) -> list[str]:
        lines: list[str] = []
        current = start_id
        seen: set[str] = set()
        while current:
            if current in seen:
                self.warnings.append(f"cycle detected in next chain at {current}")
                break
            seen.add(current)
            block = self.blocks.get(current)
            if block is None:
                self.warnings.append(f"missing block referenced by next: {current}")
                break
            if block.get("opcode") == "event_whenflagclicked":
                current = block.get("next")
                continue
            lines.extend(self.emit_statement(current, level))
            current = block.get("next")
        return lines

    def emit_statement(self, block_id: str, level: int) -> list[str]:
        block = self.blocks[block_id]
        opcode = block.get("opcode", "")
        indent = "  " * level

        if opcode == "event_whenflagclicked":
            return self.emit_chain(block.get("next"), level)
        if opcode == "combined_motor_starting":
            port = self.port_number(self.input_value(block, "PORT", "E+F"))
            return [f"{indent}_motor.pair({port},{int(field(block, 'STATUS', '3'))})"]
        if opcode == "combined_motor_stopping":
            return [f"{indent}_motor.mov_set_stop_module({int(field(block, 'status', '1'))})"]
        if opcode == "combined_motor_startWithPower":
            return [f"{indent}_motor.mov_power({self.input_value(block, 'POWER_ONE')}, {self.input_value(block, 'POWER_TWO')})"]
        if opcode == "combined_motor_startWithPowerObj":
            return [f"{indent}_motor.mov_for_power_seconds({self.input_value(block, 'POWER_ONE')}, {self.input_value(block, 'POWER_TWO')}, {self.input_value(block, 'COUNT')})"]
        if opcode == "combined_mov_dir_power":
            direction = field(block, "DIRECTION", "advance")
            power = self.input_value(block, "POWER")
            return [f'{indent}_motor.mov_dir_power("{direction}", {power})']
        if opcode == "combined_mov_dir_power_seconds":
            direction = field(block, "DIRECTION", "advance")
            power = self.input_value(block, "POWER")
            seconds = self.input_value(block, "SECONDS")
            return [f'{indent}_motor.mov_dir_power_seconds("{direction}", {power}, {seconds})']
        if opcode == "combined_motor_stop":
            return [f"{indent}_motor.mov_stop()"]
        if opcode == "combined_linepatrolInit":
            return [f"{indent}_motor.mov_find_line_init()"]
        if opcode == "combined_linepatrol_ltr":
            values = [self.port_input(block, name) for name in ("PORT_ONE", "PORT_TWO")]
            values.extend(self.input_value(block, name) for name in ("LEFT", "RIGHT", "KP", "KD"))
            return [f"{indent}_motor.mov_find_line_run({', '.join(values)})"]
        if opcode == "set_color_threshold_value":
            port = self.port_input(block, "PORT")
            threshold = self.input_value(block, "THRESHOLD", "500")
            return [f"{indent}_color.set_color_threshold_value({port}, {threshold})"]
        if opcode == "control_wait":
            return [f"{indent}_os.sleep_s({self.input_value(block, 'DURATION', '0')})"]
        if opcode == "control_break":
            return [f"{indent}break"]
        if opcode == "control_stop":
            return [f"{indent}_os.stop_exit()"]
        if opcode == "control_wait_until":
            condition = self.condition_code(block)
            return [
                f"{indent}while not ({condition}):",
                f"{indent}  _os.sleep_s(0.001)",
            ]
        if opcode == "control_repeat_until":
            condition = self.condition_code(block)
            lines = [f"{indent}while not ({condition}):"]
            body = self.emit_chain(self.input_block_id(block, "SUBSTACK"), level + 1)
            lines.extend(body or [f"{indent}  pass"])
            lines.append(f"{indent}  _os.sleep_s(0.001)")
            return lines
        if opcode == "control_forever":
            lines = [f"{indent}while True:"]
            substack = self.input_block_id(block, "SUBSTACK")
            lines.extend(self.emit_chain(substack, level + 1))
            # Preserve Spark AI's existing placement for forever-loop sleep.
            lines.append(f"{indent}{'  ' * 2}_os.sleep_s(0.001)")
            return lines
        if opcode == "control_if":
            lines = [f"{indent}if {self.condition_code(block)}:"]
            substack = self.input_block_id(block, "SUBSTACK")
            body = self.emit_chain(substack, level + 1)
            lines.extend(body or [f"{indent}  pass"])
            return lines
        if opcode == "control_if_else":
            lines = [f"{indent}if {self.condition_code(block)}:"]
            then_body = self.emit_chain(self.input_block_id(block, "SUBSTACK"), level + 1)
            lines.extend(then_body or [f"{indent}  pass"])
            lines.append(f"{indent}else:")
            else_body = self.emit_chain(self.input_block_id(block, "SUBSTACK2"), level + 1)
            lines.extend(else_body or [f"{indent}  pass"])
            return lines
        if opcode == "control_repeat":
            lines = [f"{indent}for count in range({self.input_value(block, 'TIMES', '0')}):"]
            body = self.emit_chain(self.input_block_id(block, "SUBSTACK"), level + 1)
            lines.extend(body or [f"{indent}  pass"])
            lines.append(f"{indent}  _os.sleep_s(0.001)")
            return lines
        if opcode == "data_setvariableto":
            variable = self.variable_from_field(block)
            return [f"{indent}{variable} = {self.input_value(block, 'VALUE', '0')}"]
        if opcode == "data_changevariableby":
            variable = self.variable_from_field(block)
            return [f"{indent}{variable} += {self.input_value(block, 'VALUE', '0')}"]
        if opcode == "procedures_call":
            return [f"{indent}{self.custom_call_code(block)}"]
        if opcode == "procedures_definition":
            return []
        if opcode == "data_addtolist":
            list_name = self.list_from_field(block)
            return [f"{indent}{list_name}.append({self.list_item_input(block)})"]
        if opcode == "data_insertatlist":
            list_name = self.list_from_field(block)
            index = self.input_value(block, "INDEX", "1")
            item = self.list_item_input(block)
            return [f"{indent}{list_name}.insert({index}, {item})"]
        if opcode == "data_replaceitemoflist":
            list_name = self.list_from_field(block)
            index = self.input_value(block, "INDEX", "1")
            item = self.list_item_input(block)
            return [f"{indent}{list_name}.set({index}, {item})"]
        if opcode == "data_deleteoflist":
            list_name = self.list_from_field(block)
            return [f"{indent}{list_name}.remove_index({self.input_value(block, 'INDEX', '1')})"]
        if opcode == "data_deletealloflist":
            return [f"{indent}{self.list_from_field(block)}.remove_all()"]
        if opcode == "matrix_lamp":
            return [f"{indent}_matrix.show({matrix_rows_to_hex(field(block, 'lamp', '0' * 35))})"]
        if opcode == "combined_motor_line":
            line = field(block, "line", "advance").lower()
            distance = self.input_value(block, "distance", "0")
            unit = field(block, "unit", "seconds")
            return [f'{indent}_motor.mov_for_degrees("{line}", {distance}, "{unit}")']
        if opcode == "combined_forward_offset":
            left = self.input_value(block, "LEFT_OFFSET", "0")
            right = self.input_value(block, "RIGHT_OFFSET", "0")
            return [f"{indent}_motor.mov_set_advance_offset({left}, {right})"]
        if opcode == "combined_backward_offset":
            left = self.input_value(block, "LEFT_OFFSET", "0")
            right = self.input_value(block, "RIGHT_OFFSET", "0")
            return [f"{indent}_motor.mov_set_retreat_offset({left}, {right})"]
        if opcode == "motor_startWithPower":
            port = self.port_input(block, "PORT")
            power = self.input_value(block, "POWER")
            return [f"{indent}_motor.run_power({port},{power})"]
        if opcode == "motor_specifiedunit":
            port = self.port_input(block, "PORT")
            power = self.input_value(block, "POWER")
            count = self.input_value(block, "COUNT")
            return [f"{indent}_motor.run_for_power_seconds({port}, {power}, {count})"]
        if opcode == "motor_stop":
            return [f"{indent}_motor.stop({self.port_input(block, 'PORT')})"]
        if opcode == "motor_specified_manner":
            port = self.port_input(block, "PORT")
            action = int(field(block, "action", "1"))
            return [f"{indent}_motor.stop_module({port}, {action})"]
        if opcode == "motor_reset_operating_degree":
            return [f"{indent}_motor.reset_relative_position({self.port_input(block, 'PORT')})"]
        if opcode == "matrix_lamp_stop":
            return [f"{indent}_matrix.clear()"]
        if opcode == "matrix_lamp_text":
            value = self.input_value(block, "matrix_text", "''")
            return [f"{indent}_matrix.show_roll(str({value}))"]
        if opcode == "matrix_lamp_set":
            return [f"{indent}_matrix.set_brightness({int(field(block, 'brightness', '0'))})"]
        if opcode == "matrix_lamp_single":
            x = self.input_value(block, "x", "0")
            y = self.input_value(block, "y", "0")
            on_off = field(block, "switchOnOff", "1")
            return [f"{indent}_matrix.set_pixel_brightness({x},{y},{on_off})"]
        if opcode == "sound_stopallsounds":
            return [f"{indent}_beep.stop()"]
        if opcode in {"sound_play", "sound_playuntildone"}:
            sound = self.input_value(block, "SOUND_MENU", "0")
            sound = sound.strip('"\'')
            method = "start" if opcode == "sound_play" else "untildone"
            return [f'{indent}_beep.{method}("{sound}.wav")']
        if opcode == "sound_setvolumeto":
            return [f"{indent}_beep.setvolumeto({self.input_value(block, 'VOLUME', '0')})"]
        if opcode == "sound_PlayMusic":
            note = self.input_value(block, "NOTE", "C").strip('"\'').lower()
            beats = self.input_value(block, "BEATS", "0.25")
            return [f'{indent}_beep.play_muic("{note}", {beats})']
        if opcode == "sensing_reset_timer":
            return [f"{indent}_os.resetTimer()"]
        if opcode == "sensing_set_yaw_angle":
            return [f"{indent}_mem.restyaw()"]

        self.record_unsupported(block_id, block)
        return [f"{indent}# unsupported block: {opcode}"]

    def generate(self) -> GeneratorResult:
        procedures = self.collect_custom_procedures()
        lines: list[str] = []
        for procedure in procedures:
            lines.extend(self.custom_definition_lines(procedure))
            lines.append("")
        top_level = [
            (block_id, block)
            for block_id, block in self.blocks.items()
            if block.get("topLevel")
            and not block.get("shadow")
            and block.get("opcode") != "procedures_definition"
        ]
        top_level.sort(key=lambda item: (item[1].get("y", 0), item[1].get("x", 0)))
        if not top_level:
            self.warnings.append("project has no top-level blocks")
        for block_id, _ in top_level:
            lines.extend(self.emit_chain(block_id, 0))
        code = "\n".join(lines).rstrip() + ("\n" if lines else "")
        return GeneratorResult(code=code, unsupported=self.unsupported, warnings=self.warnings)


def normalize_code(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    try:
        tree = ast.parse(text, mode="exec")
        _clean_runtime_sleeps(tree)
        return ast.unparse(tree).strip() + "\n"
    except SyntaxError:
        # Keep a useful line-based fallback for incomplete or diagnostic code.
        pass
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.rstrip() + ("\n" if text.strip() else "")


def project_summary(project: ProjectData) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    for target in project.data.get("targets", []):
        blocks = get_blocks(target)
        targets.append(
            {
                "name": target.get("name"),
                "isStage": bool(target.get("isStage")),
                "blockCount": len(blocks),
                "opcodes": dict(sorted(Counter(str(b.get("opcode", "")) for b in blocks.values()).items())),
                "costumeCount": len(target.get("costumes", [])),
                "soundCount": len(target.get("sounds", [])),
                "variableCount": len(target.get("variables", {})),
                "listCount": len(target.get("lists", {})),
            }
        )
    return {
        "file": str(project.path),
        "archiveEntries": project.entries,
        "meta": project.data.get("meta", {}),
        "targets": targets,
    }


def validate_project(project: ProjectData) -> list[str]:
    issues: list[str] = []
    targets = project.data.get("targets", [])
    variable_ids = set(stage_variables(project))
    list_ids = set(stage_lists(project))
    if not any(isinstance(target, dict) and target.get("isStage") for target in targets):
        issues.append("project has no stage target")
    if not sprite_targets(project):
        issues.append("project has no sprite target")
    all_blocks = {
        block_id: block
        for target in targets
        if isinstance(target, dict)
        for block_id, block in get_blocks(target).items()
    }
    if any(
        block.get("opcode") == "set_color_threshold_value"
        for block in all_blocks.values()
        if isinstance(block, dict)
    ):
        issues.append(
            "project contains set_color_threshold_value; Spark AI 1.1.9 can "
            "save this threshold block but may fail to reload the project"
        )
    required_extensions = project_extensions_for_blocks(all_blocks)
    if required_extensions and project.data.get("extensions") != required_extensions:
        issues.append(
            "project extensions should be "
            f"{required_extensions!r} for the generated blocks, got "
            f"{project.data.get('extensions')!r}"
        )

    def check_variable_or_list_reference(
        target_name: str,
        block_id: str,
        location: str,
        reference: Any,
    ) -> None:
        if not isinstance(reference, list) or len(reference) < 3:
            return
        primitive_type, display_name, reference_id = reference[:3]
        if primitive_type == 12 and str(reference_id) not in variable_ids:
            issues.append(
                f"{target_name}:{block_id} {location} references missing stage "
                f"variable {reference_id} ({display_name})"
            )
        elif primitive_type == 13 and str(reference_id) not in list_ids:
            issues.append(
                f"{target_name}:{block_id} {location} references missing stage "
                f"list {reference_id} ({display_name})"
            )

    archive_entries = set(project.entries)
    for target in targets:
        if not isinstance(target, dict):
            issues.append("target entry is not an object")
            continue
        name = str(target.get("name", "<unnamed>"))
        blocks = get_blocks(target)
        ids = set(blocks)
        for block_id, block in blocks.items():
            next_id = block.get("next")
            parent_id = block.get("parent")
            if next_id and next_id not in ids:
                issues.append(f"{name}:{block_id} next references missing block {next_id}")
            if parent_id and parent_id not in ids:
                issues.append(f"{name}:{block_id} parent references missing block {parent_id}")
            for field_name, field_value in block.get("fields", {}).items():
                if not isinstance(field_value, list) or len(field_value) < 2:
                    continue
                field_id = field_value[1]
                if field_id is None:
                    continue
                if field_name == "VARIABLE" and str(field_id) not in variable_ids:
                    issues.append(
                        f"{name}:{block_id} field {field_name} references missing "
                        f"stage variable {field_id} ({field_value[0]})"
                    )
                elif field_name == "LIST" and str(field_id) not in list_ids:
                    issues.append(
                        f"{name}:{block_id} field {field_name} references missing "
                        f"stage list {field_id} ({field_value[0]})"
                    )
            for input_name, entry in block.get("inputs", {}).items():
                if not isinstance(entry, list):
                    issues.append(f"{name}:{block_id} input {input_name} is not an array")
                    continue
                for candidate in entry[1:]:
                    if isinstance(candidate, str) and candidate and candidate not in ids:
                        issues.append(f"{name}:{block_id} input {input_name} references missing block {candidate}")
                    elif isinstance(candidate, list):
                        check_variable_or_list_reference(
                            name,
                            block_id,
                            f"input {input_name}",
                            candidate,
                        )

        for costume in target.get("costumes", []):
            asset = costume.get("md5ext") if isinstance(costume, dict) else None
            if asset and asset not in archive_entries:
                issues.append(f"{name} costume asset is missing: {asset}")
        for sound in target.get("sounds", []):
            asset = sound.get("md5ext") if isinstance(sound, dict) else None
            if asset and asset not in archive_entries:
                issues.append(f"{name} sound asset is missing: {asset}")
    return issues


def reference_diff(expected: str, actual: str) -> str:
    return "".join(
        difflib.unified_diff(
            normalize_code(expected).splitlines(keepends=True),
            normalize_code(actual).splitlines(keepends=True),
            fromfile="reference.py",
            tofile="generated.py",
        )
    )


def command_inspect(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project))
    targets = sprite_targets(project)
    if not targets:
        raise ProjectFormatError("project has no sprite target")

    result = PythonGenerator(targets[0], stage_variables(project), stage_lists(project)).generate()
    summary = project_summary(project)
    if args.json:
        payload = {
            "summary": summary,
            "generatedPython": result.code,
            "unsupported": result.unsupported,
            "warnings": result.warnings,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Project: {project.path}")
        print(f"Archive entries: {len(project.entries)}")
        for target in summary["targets"]:
            print(f"Target {target['name']}: {target['blockCount']} blocks")
        print("\nGenerated Python:")
        print(result.code or "<empty>")
        if result.unsupported:
            print("Unsupported blocks:")
            for item in result.unsupported:
                print(f"  - {item['opcode']} ({item['id']})")
        if result.warnings:
            print("Warnings:")
            for warning in result.warnings:
                print(f"  - {warning}")
    if args.report:
        payload = {
            "summary": summary,
            "generatedPython": result.code,
            "unsupported": result.unsupported,
            "warnings": result.warnings,
        }
        Path(args.report).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def command_compare(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project))
    targets = sprite_targets(project)
    if not targets:
        raise ProjectFormatError("project has no sprite target")
    result = PythonGenerator(targets[0], stage_variables(project), stage_lists(project)).generate()
    expected = Path(args.reference).read_text(encoding="utf-8")
    diff = reference_diff(expected, result.code)
    if diff:
        print("FAIL: generated Python differs from reference")
        print(diff, end="")
        return 1
    if result.unsupported:
        print("FAIL: generated Python matched, but unsupported blocks were present")
        for item in result.unsupported:
            print(f"  - {item['opcode']} ({item['id']})")
        return 1
    print("PASS: generated Python matches the reference")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project))
    issues = validate_project(project)
    result_items: list[dict[str, Any]] = []
    for target in sprite_targets(project):
        generated = PythonGenerator(target, stage_variables(project), stage_lists(project)).generate()
        result_items.append(
            {
                "target": target.get("name"),
                "unsupported": generated.unsupported,
                "warnings": generated.warnings,
            }
        )
    unsupported = [item for result in result_items for item in result["unsupported"]]
    warnings = [item for result in result_items for item in result["warnings"]]
    if args.json:
        print(
            json.dumps(
                {
                    "valid": not issues and not unsupported,
                    "structuralIssues": issues,
                    "unsupported": unsupported,
                    "warnings": warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if issues:
            print("Structural issues:")
            for issue in issues:
                print(f"  - {issue}")
        if unsupported:
            print("Unsupported blocks:")
            for item in unsupported:
                print(f"  - {item['opcode']} ({item['id']})")
        if warnings:
            print("Warnings:")
            for warning in warnings:
                print(f"  - {warning}")
        if not issues and not unsupported:
            print("PASS: project structure and supported opcode checks passed")
    return 1 if issues or unsupported else 0


def command_generate(args: argparse.Namespace) -> int:
    source_path = Path(args.source)
    source = sys.stdin.read() if args.source == "-" else source_path.read_text(encoding="utf-8")
    output = Path(args.output) if args.output else unique_output_path(Path(args.output_dir))
    result = compile_project(source, Path(args.template), output)
    print(f"Generated: {result.path}")
    print(f"Blocks: {result.block_count}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="inspect a project and generate Python")
    inspect_parser.add_argument("project")
    inspect_parser.add_argument("--json", action="store_true", help="print a JSON report")
    inspect_parser.add_argument("--report", help="write a JSON report")
    inspect_parser.set_defaults(func=command_inspect)

    compare_parser = subparsers.add_parser("compare", help="compare generated Python with a reference file")
    compare_parser.add_argument("project")
    compare_parser.add_argument("reference")
    compare_parser.set_defaults(func=command_compare)

    validate_parser = subparsers.add_parser("validate", help="validate project structure and supported opcodes")
    validate_parser.add_argument("project")
    validate_parser.add_argument("--json", action="store_true", help="print a JSON report")
    validate_parser.set_defaults(func=command_validate)

    generate_parser = subparsers.add_parser("generate", help="compile Spark AI Python into a new .sparkai file")
    generate_parser.add_argument("source", help="Python file, or - to read from stdin")
    generate_parser.add_argument(
        "--template",
        default=str(Path(__file__).resolve().parents[1] / "templates" / "base.sparkai"),
        help="fixed .sparkai template",
    )
    generate_parser.add_argument("--output", help="explicit output path")
    generate_parser.add_argument("--output-dir", default="generated", help="directory for an automatic output name")
    generate_parser.set_defaults(func=command_generate)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return args.func(args)
    except (OSError, ProjectFormatError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
