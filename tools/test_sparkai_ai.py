import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from sparkai_ai import (  # noqa: E402
    AIJSONError,
    SparkAIAIError,
    build_generation_user_prompt,
    build_system_prompt,
    compact_conversation_summary,
    generate_with_deepseek,
    parse_ai_json,
    request_ai_response,
    validate_sparkai_python,
)


class SparkAITests(unittest.TestCase):
    def test_system_prompt_includes_rules_hardware_and_functions(self):
        prompt = build_system_prompt()
        self.assertIn("ai_generation_rules.md", prompt)
        self.assertIn("conversation_state.md", prompt)
        self.assertIn("hardware_overview.md", prompt)
        self.assertIn("supported_functions.md", prompt)
        self.assertIn("block_semantics.md", prompt)
        self.assertIn("supported_blocks.md", prompt)
        self.assertIn("_motor.mov_find_line_run", prompt)
        self.assertIn("_key.key_remote", prompt)
        self.assertIn("灰度传感器阈值设置", prompt)
        self.assertIn("_color.set_color_threshold_value(port, threshold)", prompt)
        self.assertNotIn("不要使用 `_color.set_color_threshold_value(...)`", prompt)
        self.assertNotIn("不要生成这个函数", prompt)
        self.assertIn("A=0", prompt)

    def test_generation_prompt_contains_state_summary_and_request(self):
        prompt = build_generation_user_prompt(
            "做一个巡线小车",
            project_state='{"left_motor":"E","current_python":"_motor.mov_stop()\\n"}',
            conversation_summary="用户要巡线",
        )
        self.assertIn("做一个巡线小车", prompt)
        self.assertIn('"left_motor":"E"', prompt)
        self.assertIn("_motor.mov_stop()", prompt)
        self.assertIn("用户要巡线", prompt)
        self.assertIn("Latest user request:", prompt)
        self.assertIn("Current candidate Python:", prompt)
        self.assertIn("Use the loaded rule files", prompt)

    def test_conversation_summary_is_bounded_before_prompting(self):
        summary = "old question\n" + ("x" * 9000) + "\nlatest answer"
        compact = compact_conversation_summary(summary, limit=100)
        self.assertTrue(compact.startswith("[earlier conversation omitted]"))
        self.assertNotIn("old question", compact)
        self.assertIn("latest answer", compact)

        prompt = build_generation_user_prompt(
            "继续",
            conversation_summary=summary,
        )
        self.assertIn("[earlier conversation omitted]", prompt)
        self.assertNotIn("old question", prompt)

    def test_parse_valid_code_json(self):
        response = parse_ai_json(json.dumps({
            "type": "code",
            "message": "ok",
            "python": "_motor.mov_stop()\n",
            "assumptions": ["demo"],
            "needs_clarification": False,
            "questions": [],
            "hardware_config": {"left_motor": "E"},
        }))
        self.assertEqual(response.type, "code")
        self.assertEqual(response.python, "_motor.mov_stop()\n")
        self.assertEqual(response.assumptions, ("demo",))
        self.assertEqual(response.hardware_config["left_motor"], "E")

    def test_parse_rejects_invalid_json(self):
        with self.assertRaises(AIJSONError):
            parse_ai_json("{\"type\": \"code\"")

    def test_parse_accepts_json_code_fence(self):
        response = parse_ai_json('```json\n{"type":"question","message":"请确认","questions":[]}\n```')
        self.assertEqual(response.type, "question")

    def test_request_ai_response_retries_incomplete_json(self):
        incomplete = '{"type":"code","message":"未完成'
        complete = json.dumps({
            "type": "question",
            "message": "请确认电机端口",
            "python": "",
            "questions": ["电机接哪个端口？"],
        })
        with patch("sparkai_ai.deepseek_chat_completion", side_effect=[incomplete, complete]) as call:
            response = request_ai_response(
                api_key="test-key",
                messages=[{"role": "user", "content": "生成程序"}],
                model="test-model",
                base_url="https://example.invalid",
            )
        self.assertEqual(response.type, "question")
        self.assertEqual(call.call_count, 2)

    def test_validate_sparkai_python_returns_error_text(self):
        self.assertEqual(validate_sparkai_python("_motor.mov_stop()\n"), "")
        error = validate_sparkai_python("_beep.start()\n")
        self.assertIn("unsupported Spark AI function: _beep.start", error)
        self.assertEqual(validate_sparkai_python("_color.set_color_threshold_value(0, 500)\n"), "")

    def test_generate_repairs_invalid_python(self):
        bad = json.dumps({
            "type": "code",
            "message": "bad",
            "python": "_beep.start()\n",
            "assumptions": [],
            "needs_clarification": False,
            "questions": [],
            "hardware_config": {},
        })
        fixed = json.dumps({
            "type": "code",
            "message": "fixed",
            "python": "_beep.play_muic(\"c\", 0.25)\n",
            "assumptions": [],
            "needs_clarification": False,
            "questions": [],
            "hardware_config": {},
        })
        with patch("sparkai_ai.deepseek_chat_completion", side_effect=[bad, fixed]):
            result = generate_with_deepseek("响一声", api_key="test-key")
        self.assertTrue(result.validated)
        self.assertEqual(result.repair_attempts, 1)


if __name__ == "__main__":
    unittest.main()
