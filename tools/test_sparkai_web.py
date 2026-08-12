import json
import os
import sys
import threading
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import sparkai_web  # noqa: E402
from sparkai_ai import AIResponse, GenerationResult  # noqa: E402


class QuietSparkAIHandler(sparkai_web.SparkAIHandler):
    def log_message(self, format, *args):
        pass


class WebConfigTests(unittest.TestCase):
    def test_read_env_file_value_supports_comments_and_quotes(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "\ufeff# local defaults\nOTHER=value\nDEEPSEEK_API_KEY=\"local-key\"\n",
                encoding="utf-8",
            )

            self.assertEqual(
                sparkai_web.read_env_file_value(env_file, "DEEPSEEK_API_KEY"),
                "local-key",
            )

    def test_resolve_api_key_prefers_request_then_local_then_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("DEEPSEEK_API_KEY=local-key\n", encoding="utf-8")

            with patch.object(sparkai_web, "LOCAL_ENV_FILE", env_file), patch.dict(
                os.environ,
                {"DEEPSEEK_API_KEY": "environment-key"},
            ):
                self.assertEqual(sparkai_web.resolve_api_key("request-key"), "request-key")
                self.assertEqual(sparkai_web.resolve_api_key(""), "local-key")

            env_file.unlink()
            with patch.object(sparkai_web, "LOCAL_ENV_FILE", env_file), patch.dict(
                os.environ,
                {"DEEPSEEK_API_KEY": "environment-key"},
            ):
                self.assertEqual(sparkai_web.resolve_api_key(""), "environment-key")


class WebServerCase(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietSparkAIHandler)
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def post_json(self, path, payload):
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_chat_endpoint_calls_ai_and_returns_validated_python(self):
        ai_response = AIResponse(
            type="code",
            message="已生成巡线程序",
            python="_motor.mov_stop()\n",
            assumptions=("电机接 E/F",),
            needs_clarification=False,
            questions=(),
            hardware_config={"left_motor": "E"},
            raw={
                "type": "code",
                "message": "已生成巡线程序",
                "python": "_motor.mov_stop()\n",
                "assumptions": ["电机接 E/F"],
                "needs_clarification": False,
                "questions": [],
                "hardware_config": {"left_motor": "E"},
            },
        )

        with patch("sparkai_web.generate_with_deepseek", return_value=GenerationResult(ai_response)) as generate:
            status, payload = self.post_json(
                "/chat",
                {
                    "message": "生成一个巡线小车",
                    "api_key": "test-key",
                    "conversation_summary": "user: 使用 E/F 电机",
                    "current_python": "_motor.mov_power(20, 20)\n",
                },
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["validated"])
        self.assertEqual(payload["validation_error"], "")
        self.assertEqual(payload["response"]["python"], "_motor.mov_stop()\n")
        generate.assert_called_once()
        _, kwargs = generate.call_args
        self.assertEqual(kwargs["api_key"], "test-key")
        self.assertIn("使用 E/F 电机", kwargs["conversation_summary"])
        self.assertEqual(
            json.loads(kwargs["project_state"]),
            {
                "has_current_python": True,
                "current_python": "_motor.mov_power(20, 20)\n",
            },
        )

    def test_chat_endpoint_rejects_empty_message(self):
        request = urllib.request.Request(
            self.base_url + "/chat",
            data=json.dumps({"message": "   ", "api_key": "test-key"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)

        self.assertEqual(error.exception.code, 400)
        payload = json.loads(error.exception.read().decode("utf-8"))
        self.assertIn("用户需求不能为空", payload["error"])

    def test_generate_endpoint_still_creates_clipboard_xml(self):
        form = urllib.parse.urlencode({
            "python": "_motor.mov_stop()\n",
            "action": "clipboard",
        }).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/generate",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertIn("剪贴板 XML", body)
        self.assertIn("combined_motor_stop", body)

    def test_generate_page_includes_new_session_button(self):
        with urllib.request.urlopen(self.base_url + "/generate", timeout=5) as response:
            body = response.read().decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertIn("新建会话", body)
        self.assertIn("CHAT_STORAGE_KEY", body)


if __name__ == "__main__":
    unittest.main()
