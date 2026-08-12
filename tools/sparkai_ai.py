#!/usr/bin/env python3
"""Generate Spark AI Python with a DeepSeek-compatible chat API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from .sparkai_reverse import ReverseCodeError, SparkAIReverseCompiler
except ImportError:
    from sparkai_reverse import ReverseCodeError, SparkAIReverseCompiler


ROOT = Path(__file__).resolve().parents[1]
AI_RULE_FILES = (
    ROOT / "docs" / "ai_rules" / "ai_generation_rules.md",
    ROOT / "docs" / "ai_rules" / "hardware_overview.md",
    ROOT / "docs" / "ai_rules" / "block_semantics.md",
    ROOT / "docs" / "ai_rules" / "supported_functions.md",
)
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


class SparkAIAIError(ValueError):
    """User-facing AI integration error."""


@dataclass(frozen=True)
class AIResponse:
    type: str
    message: str
    python: str
    assumptions: tuple[str, ...]
    needs_clarification: bool
    questions: tuple[str, ...]
    hardware_config: dict[str, Any]
    raw: dict[str, Any]


@dataclass(frozen=True)
class GenerationResult:
    response: AIResponse
    validation_error: str = ""
    repair_attempts: int = 0

    @property
    def validated(self) -> bool:
        return bool(self.response.python) and not self.validation_error


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SparkAIAIError(f"cannot read AI rule file {path}: {exc}") from exc


def load_rule_context() -> str:
    parts = []
    for path in AI_RULE_FILES:
        parts.append(f"## FILE: {path.relative_to(ROOT).as_posix()}\n\n{read_text(path)}")
    return "\n\n---\n\n".join(parts)


def build_system_prompt() -> str:
    return (
        "You are the AI code-generation layer for Spark AI Python to Blocks.\n"
        "Follow the project rule files below exactly. Return JSON only.\n\n"
        + load_rule_context()
    )


def build_generation_user_prompt(
    user_request: str,
    *,
    project_state: str = "{}",
    conversation_summary: str = "",
) -> str:
    return (
        "Project state JSON:\n"
        f"{project_state.strip() or '{}'}\n\n"
        "Conversation summary:\n"
        f"{conversation_summary.strip() or '(none)'}\n\n"
        "If Project state JSON contains current_python, treat it as the current candidate program. "
        "When the latest user request asks for a change, modify that candidate and return the full updated Python program, "
        "not a patch and not only the changed lines.\n\n"
        "Latest user request:\n"
        f"{user_request.strip()}\n\n"
        "Generate Spark AI Python or ask clarification questions."
    )


def build_repair_user_prompt(
    *,
    original_user_request: str,
    project_state: str,
    failed_python: str,
    validation_error: str,
) -> str:
    return (
        "Original user request:\n"
        f"{original_user_request.strip()}\n\n"
        "Project state JSON:\n"
        f"{project_state.strip() or '{}'}\n\n"
        "Validation error from local converter:\n"
        f"{validation_error.strip()}\n\n"
        "Failed Python:\n"
        f"{failed_python.strip()}\n\n"
        "Return a full corrected JSON response. Keep the user's requested behavior and mappings."
    )


def deepseek_chat_completion(
    *,
    api_key: str,
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 60,
    max_tokens: int = 4096,
) -> str:
    if not api_key:
        raise SparkAIAIError("DEEPSEEK_API_KEY is not set")
    endpoint = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SparkAIAIError(f"DeepSeek API HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SparkAIAIError(f"DeepSeek API request failed: {exc}") from exc

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SparkAIAIError(f"unexpected DeepSeek API response: {data!r}") from exc


def parse_ai_json(content: str) -> AIResponse:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SparkAIAIError(f"AI response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SparkAIAIError("AI response JSON must be an object")

    response_type = str(data.get("type", "")).strip()
    if response_type not in {"code", "question", "explanation"}:
        raise SparkAIAIError(f"AI response has invalid type: {response_type!r}")

    python_code = data.get("python", "")
    if python_code is None:
        python_code = ""
    if not isinstance(python_code, str):
        raise SparkAIAIError("AI response field 'python' must be a string")

    questions = data.get("questions", [])
    if not isinstance(questions, list):
        raise SparkAIAIError("AI response field 'questions' must be a list")

    assumptions = data.get("assumptions", [])
    if not isinstance(assumptions, list):
        raise SparkAIAIError("AI response field 'assumptions' must be a list")

    hardware_config = data.get("hardware_config", {})
    if not isinstance(hardware_config, dict):
        raise SparkAIAIError("AI response field 'hardware_config' must be an object")

    return AIResponse(
        type=response_type,
        message=str(data.get("message", "")),
        python=python_code,
        assumptions=tuple(str(item) for item in assumptions),
        needs_clarification=bool(data.get("needs_clarification", False)),
        questions=tuple(str(item) for item in questions),
        hardware_config=hardware_config,
        raw=data,
    )


def validate_sparkai_python(source: str) -> str:
    try:
        SparkAIReverseCompiler().compile(source)
    except ReverseCodeError as exc:
        return str(exc)
    return ""


def generate_with_deepseek(
    user_request: str,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    project_state: str = "{}",
    conversation_summary: str = "",
    max_repairs: int = 2,
) -> GenerationResult:
    system_prompt = build_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": build_generation_user_prompt(
                user_request,
                project_state=project_state,
                conversation_summary=conversation_summary,
            ),
        },
    ]
    response = parse_ai_json(
        deepseek_chat_completion(
            api_key=api_key,
            messages=messages,
            model=model,
            base_url=base_url,
        )
    )
    if response.type != "code" or not response.python:
        return GenerationResult(response=response)

    validation_error = validate_sparkai_python(response.python)
    repairs = 0
    while validation_error and repairs < max_repairs:
        repairs += 1
        repair_messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": build_repair_user_prompt(
                    original_user_request=user_request,
                    project_state=project_state,
                    failed_python=response.python,
                    validation_error=validation_error,
                ),
            },
        ]
        response = parse_ai_json(
            deepseek_chat_completion(
                api_key=api_key,
                messages=repair_messages,
                model=model,
                base_url=base_url,
            )
        )
        if response.type != "code" or not response.python:
            return GenerationResult(
                response=response,
                validation_error=validation_error,
                repair_attempts=repairs,
            )
        validation_error = validate_sparkai_python(response.python)

    return GenerationResult(
        response=response,
        validation_error=validation_error,
        repair_attempts=repairs,
    )


def command_prompt(args: argparse.Namespace) -> int:
    print(build_system_prompt())
    return 0


def command_generate(args: argparse.Namespace) -> int:
    request_text = args.request
    if args.request_file:
        request_text = Path(args.request_file).read_text(encoding="utf-8")
    if not request_text.strip():
        raise SparkAIAIError("request is empty")

    project_state = args.project_state
    if args.project_state_file:
        project_state = Path(args.project_state_file).read_text(encoding="utf-8")

    result = generate_with_deepseek(
        request_text,
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        model=args.model,
        base_url=args.base_url,
        project_state=project_state,
        conversation_summary=args.conversation_summary,
        max_repairs=args.max_repairs,
    )

    output = {
        "validated": result.validated,
        "validation_error": result.validation_error,
        "repair_attempts": result.repair_attempts,
        "response": result.response.raw,
    }
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0 if result.validated or result.response.needs_clarification else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prompt_parser = subparsers.add_parser("prompt", help="print the assembled system prompt")
    prompt_parser.set_defaults(func=command_prompt)

    generate_parser = subparsers.add_parser("generate", help="call DeepSeek and validate Spark AI Python")
    generate_parser.add_argument("request", nargs="?", default="", help="user request text")
    generate_parser.add_argument("--request-file", help="read user request from a UTF-8 text file")
    generate_parser.add_argument("--project-state", default="{}", help="compact project-state JSON")
    generate_parser.add_argument("--project-state-file", help="read project-state JSON from a file")
    generate_parser.add_argument("--conversation-summary", default="", help="short conversation summary")
    generate_parser.add_argument("--model", default=DEFAULT_MODEL)
    generate_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    generate_parser.add_argument("--max-repairs", type=int, default=2)
    generate_parser.set_defaults(func=command_generate)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return args.func(args)
    except (OSError, SparkAIAIError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
