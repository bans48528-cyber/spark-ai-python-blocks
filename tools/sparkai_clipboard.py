#!/usr/bin/env python3
"""Convert generated Spark AI block graphs to Blockly clipboard XML."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree as ET

try:
    from .sparkai_reverse import (
        MappingReport,
        ReverseCodeError,
        SparkAIReverseCompiler,
        mapping_report_from_compiler,
    )
except ImportError:
    from sparkai_reverse import (
        MappingReport,
        ReverseCodeError,
        SparkAIReverseCompiler,
        mapping_report_from_compiler,
    )


XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
ET.register_namespace("", XHTML_NAMESPACE)

PRIMITIVES = {
    4: ("math_number", "NUM"),
    5: ("math_positive_number", "NUM"),
    6: ("math_whole_number", "NUM"),
    7: ("math_integer", "NUM"),
    8: ("math_angle", "NUM"),
    9: ("colour_picker", "COLOUR"),
    10: ("text", "TEXT"),
    11: ("event_broadcast_menu", "BROADCAST_OPTION"),
    12: ("data_variable", "VARIABLE"),
    13: ("data_listcontents", "LIST"),
}


@dataclass(frozen=True)
class ClipboardFragment:
    kind: str
    title: str
    root_id: str
    xml: str


@dataclass(frozen=True)
class ClipboardCompileResult:
    fragments: list[ClipboardFragment]
    mapping_report: MappingReport


class BlocklyXmlSerializer:
    def __init__(
        self,
        blocks: dict[str, dict[str, Any]],
        *,
        field_id_map: dict[str, str] | None = None,
    ) -> None:
        self.blocks = blocks
        self.field_id_map = field_id_map or {}

    @staticmethod
    def tag(name: str) -> str:
        return f"{{{XHTML_NAMESPACE}}}{name}"

    @staticmethod
    def generated_id() -> str:
        return "clipboard-" + uuid4().hex

    def field_element(
        self,
        name: str,
        value: Any,
        field_id: Any = None,
    ) -> ET.Element:
        field = ET.Element(self.tag("field"), {"name": name})
        if field_id is not None:
            source_id = str(field_id)
            field.set("id", self.field_id_map.get(source_id, source_id))
            field.set("variabletype", "list" if source_id.startswith("list-") else "")
        field.text = str(value)
        return field

    def primitive_element(self, primitive: list[Any], *, shadow: bool) -> ET.Element:
        if len(primitive) < 2 or primitive[0] not in PRIMITIVES:
            primitive_type = primitive[0] if primitive else None
            raise ReverseCodeError(
                f"cannot convert Spark AI primitive type {primitive_type!r} to clipboard XML"
            )
        opcode, field_name = PRIMITIVES[primitive[0]]
        element = ET.Element(
            self.tag("shadow" if shadow else "block"),
            {"type": opcode, "id": self.generated_id()},
        )
        field_id = primitive[2] if len(primitive) >= 3 and primitive[0] in {11, 12, 13} else None
        element.append(self.field_element(field_name, primitive[1], field_id))
        return element

    def input_element(self, name: str, entry: list[Any]) -> ET.Element:
        wrapper_name = "statement" if name in {"SUBSTACK", "SUBSTACK2"} else "value"
        wrapper = ET.Element(self.tag(wrapper_name), {"name": name})
        kind = entry[0]

        def append_value(value: Any, *, shadow: bool) -> None:
            if isinstance(value, str):
                if value not in self.blocks:
                    raise ReverseCodeError(f"clipboard XML input references missing block: {value}")
                wrapper.append(self.block_element(value))
            elif isinstance(value, list):
                wrapper.append(self.primitive_element(value, shadow=shadow))
            else:
                raise ReverseCodeError(f"unsupported clipboard XML input value: {value!r}")

        if kind == 3:
            if len(entry) < 3:
                raise ReverseCodeError(f"clipboard XML input {name} is missing its shadow fallback")
            append_value(entry[2], shadow=True)
            append_value(entry[1], shadow=False)
        elif kind in {1, 2}:
            append_value(entry[1], shadow=kind == 1)
        else:
            raise ReverseCodeError(f"unsupported clipboard XML input relationship: {kind!r}")
        return wrapper

    def mutation_element(self, mutation: dict[str, Any]) -> ET.Element | None:
        attributes = {
            str(name): str(value).lower() if isinstance(value, bool) else str(value)
            for name, value in mutation.items()
            if name not in {"tagName", "children"} and value is not None
        }
        return ET.Element(self.tag("mutation"), attributes) if attributes else None

    def block_element(self, block_id: str) -> ET.Element:
        block = self.blocks[block_id]
        element = ET.Element(
            self.tag("shadow" if block.get("shadow") else "block"),
            {"type": str(block.get("opcode", "")), "id": block_id},
        )
        mutation = block.get("mutation")
        if isinstance(mutation, dict):
            mutation_element = self.mutation_element(mutation)
            if mutation_element is not None:
                element.append(mutation_element)
        for name, field_value in block.get("fields", {}).items():
            if not isinstance(field_value, list) or not field_value:
                raise ReverseCodeError(f"invalid field {name} on clipboard block {block_id}")
            field_id = field_value[1] if len(field_value) >= 2 else None
            element.append(self.field_element(name, field_value[0], field_id))
        for name, entry in block.get("inputs", {}).items():
            if not isinstance(entry, list) or len(entry) < 2:
                raise ReverseCodeError(f"invalid input {name} on clipboard block {block_id}")
            element.append(self.input_element(name, entry))
        next_id = block.get("next")
        if isinstance(next_id, str):
            next_element = ET.Element(self.tag("next"))
            next_element.append(self.block_element(next_id))
            element.append(next_element)
        return element

    def serialize(self, root_id: str) -> str:
        if root_id not in self.blocks:
            raise ReverseCodeError(f"clipboard XML root block is missing: {root_id}")
        return ET.tostring(self.block_element(root_id), encoding="unicode", short_empty_elements=True)


def _clipboard_field_id_map(compiler: SparkAIReverseCompiler) -> dict[str, str]:
    field_ids: dict[str, str] = {}
    for variable in compiler.variables.values():
        field_ids[variable.variable_id] = "clipboard-variable-" + uuid4().hex
    for list_info in compiler.lists.values():
        field_ids[list_info.list_id] = "clipboard-list-" + uuid4().hex
    return field_ids


def compile_clipboard(source: str) -> ClipboardCompileResult:
    compiler = SparkAIReverseCompiler()
    blocks, _ = compiler.compile(source)
    serializer = BlocklyXmlSerializer(blocks, field_id_map=_clipboard_field_id_map(compiler))
    fragments: list[ClipboardFragment] = []

    definitions = [
        block_id
        for block_id, block in blocks.items()
        if block.get("topLevel") and block.get("opcode") == "procedures_definition"
    ]
    for index, block_id in enumerate(definitions, start=1):
        title = f"自制积木定义 {index}"
        custom_input = blocks[block_id].get("inputs", {}).get("custom_block")
        if isinstance(custom_input, list) and len(custom_input) >= 2:
            prototype_id = custom_input[1]
            if isinstance(prototype_id, str) and prototype_id in blocks:
                proccode = blocks[prototype_id].get("mutation", {}).get("proccode")
                if proccode:
                    title = f"自制积木：{proccode}"
        fragments.append(
            ClipboardFragment(
                kind="custom",
                title=title,
                root_id=block_id,
                xml=serializer.serialize(block_id),
            )
        )

    event_id = next(
        (
            block_id
            for block_id, block in blocks.items()
            if block.get("topLevel") and block.get("opcode") == "event_whenflagclicked"
        ),
        None,
    )
    main_id = blocks[event_id].get("next") if event_id is not None else None
    if not isinstance(main_id, str):
        raise ReverseCodeError("the program does not contain a clipboard-compatible main stack")
    fragments.append(
        ClipboardFragment(
            kind="main",
            title="主程序（粘贴到启动积木下方）",
            root_id=main_id,
            xml=serializer.serialize(main_id),
        )
    )
    return ClipboardCompileResult(
        fragments=fragments,
        mapping_report=mapping_report_from_compiler(compiler),
    )


def compile_clipboard_fragments(source: str) -> list[ClipboardFragment]:
    return compile_clipboard(source).fragments
