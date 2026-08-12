import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from sparkai_ai import (  # noqa: E402
    SparkAIAIError,
    build_generation_user_prompt,
    build_system_prompt,
    generate_with_deepseek,
    parse_ai_json,
    validate_sparkai_python,
)


class SparkAITests(unittest.TestCase):
    def test_system_prompt_includes_rules_hardware_and_functions(self):
        prompt = build_system_prompt()
        self.assertIn("ai_generation_rules.md", prompt)
        self.assertIn("hardware_overview.md", prompt)
        self.assertIn("supported_functions.md", prompt)
        self.assertIn("block_semantics.md", prompt)
        self.assertIn("_motor.mov_find_line_run", prompt)
        self.assertIn("_key.key_remote", prompt)
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
        self.assertIn("full updated Python program", prompt)
        self.assertIn("用户要巡线", prompt)

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
        with self.assertRaises(SparkAIAIError):
            parse_ai_json("```json\n{}\n```")

    def test_validate_sparkai_python_returns_error_text(self):
        self.assertEqual(validate_sparkai_python("_motor.mov_stop()\n"), "")
        error = validate_sparkai_python("_beep.start()\n")
        self.assertIn("unsupported Spark AI function: _beep.start", error)

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
