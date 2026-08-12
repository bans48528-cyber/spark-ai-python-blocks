#!/usr/bin/env python3
"""Local web UI for Spark AI Python generation and block conversion."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from .sparkai_ai import SparkAIAIError, generate_with_deepseek
    from .sparkai_clipboard import ClipboardFragment, compile_clipboard
    from .sparkai_reverse import MappingReport, ReverseCodeError, compile_project, unique_output_path
except ImportError:
    from sparkai_ai import SparkAIAIError, generate_with_deepseek
    from sparkai_clipboard import ClipboardFragment, compile_clipboard
    from sparkai_reverse import MappingReport, ReverseCodeError, compile_project, unique_output_path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "base.sparkai"
OUTPUT_DIR = ROOT / "generated"
LOCAL_ENV_FILE = ROOT / ".env"


def read_env_file_value(path: Path, name: str) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return ""
    except OSError:
        return ""

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip().lstrip("\ufeff") != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value
    return ""


def default_api_key_source() -> str:
    if read_env_file_value(LOCAL_ENV_FILE, "DEEPSEEK_API_KEY"):
        return "local"
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "environment"
    return ""


def get_default_api_key() -> str:
    return read_env_file_value(LOCAL_ENV_FILE, "DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")


def resolve_api_key(request_api_key: str) -> str:
    return request_api_key.strip() or get_default_api_key()


def render_mapping_summary(report: MappingReport | None) -> str:
    if report is None:
        return ""

    sections: list[str] = []
    if report.variables:
        rows = "".join(
            f"<li><code>{html.escape(py)}</code> -> <span>{html.escape(display)}</span></li>"
            for py, display in report.variables
        )
        sections.append(f"<div><h3>变量</h3><ul>{rows}</ul></div>")
    if report.lists:
        rows = "".join(
            f"<li><code>{html.escape(py)}</code> -> <span>{html.escape(display)}</span></li>"
            for py, display in report.lists
        )
        sections.append(f"<div><h3>列表</h3><ul>{rows}</ul></div>")
    if report.unmapped_variables:
        rows = "".join(f"<li><code>{html.escape(name)}</code></li>" for name in report.unmapped_variables)
        sections.append(f"<div><h3>未映射变量</h3><ul>{rows}</ul></div>")
    if report.unmapped_lists:
        rows = "".join(f"<li><code>{html.escape(name)}</code></li>" for name in report.unmapped_lists)
        sections.append(f"<div><h3>未映射列表</h3><ul>{rows}</ul></div>")

    if not sections:
        return ""
    return '<section class="mapping-summary"><h2>映射摘要</h2>' + "".join(sections) + "</section>"


def render_clipboard_result(fragments: list[ClipboardFragment] | None) -> str:
    if not fragments:
        return ""
    items: list[str] = []
    for index, fragment in enumerate(fragments):
        target = f"clipboard-xml-{index}"
        items.append(
            '<div class="clipboard-item">'
            f'<span>{html.escape(fragment.title)}</span>'
            f'<textarea id="{target}" class="xml-source" aria-hidden="true">'
            f"{html.escape(fragment.xml)}</textarea>"
            f'<button type="button" class="copy-button" data-copy-target="{target}">复制 XML</button>'
            "</div>"
        )
    return (
        '<section class="clipboard-result"><h2>剪贴板 XML</h2>'
        + "".join(items)
        + '<p id="copy-status" class="copy-status" aria-live="polite"></p></section>'
    )


def page(
    *,
    message: str = "",
    error: bool = False,
    source: str = "",
    fragments: list[ClipboardFragment] | None = None,
    mapping_report: MappingReport | None = None,
) -> bytes:
    notice = ""
    if message:
        rendered = html.escape(message) if error else message
        notice = f'<p class="notice {"error" if error else "ok"}">{rendered}</p>'

    key_source = default_api_key_source()
    api_key_hint = {
        "local": "已配置本地默认 DeepSeek Key",
        "environment": "已从环境变量读取 DeepSeek Key",
        "": "可临时填写 DeepSeek Key",
    }[key_source]
    mapping_result = render_mapping_summary(mapping_report)
    clipboard_result = render_clipboard_result(fragments)

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Spark AI Python 转积木</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17211b;
      --muted: #66716a;
      --line: #d9e0da;
      --paper: #f6f8f5;
      --panel: #ffffff;
      --accent: #147d72;
      --accent-dark: #0d625a;
      --danger: #a33a35;
      --soft: #eef4f1;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
    main {{ width: min(1240px, calc(100% - 32px)); margin: 24px auto 44px; }}
    header {{ display: flex; justify-content: space-between; align-items: end; gap: 20px; margin-bottom: 16px; }}
    h1 {{ margin: 0; font-size: 28px; line-height: 1.15; letter-spacing: 0; }}
    header p {{ margin: 0; color: var(--muted); }}
    .layout {{ display: grid; grid-template-columns: minmax(320px, 0.85fr) minmax(420px, 1.15fr); gap: 16px; align-items: start; }}
    section, form {{ background: var(--panel); border: 1px solid var(--line); padding: 16px 18px; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    label {{ display: block; margin-bottom: 7px; font-weight: 650; }}
    textarea, input {{ border: 1px solid #b9c5bc; border-radius: 4px; color: #16251c; background: #fbfcfb; font: inherit; }}
    textarea {{ display: block; width: 100%; min-height: 420px; resize: vertical; padding: 14px; font: 14px/1.55 ui-monospace, SFMono-Regular, Consolas, monospace; tab-size: 2; }}
    textarea:focus, input:focus {{ outline: 2px solid #9fd5cd; outline-offset: 1px; border-color: var(--accent); }}
    input {{ width: 100%; padding: 10px 11px; }}
    button {{ border: 0; border-radius: 4px; padding: 10px 16px; background: var(--accent); color: white; font: 650 15px inherit; cursor: pointer; }}
    button:hover {{ background: var(--accent-dark); }}
    button:disabled {{ opacity: 0.55; cursor: wait; }}
    .secondary {{ background: #3f5f58; }}
    .secondary:hover {{ background: #304b45; }}
    .ghost {{ background: transparent; color: var(--accent-dark); border: 1px solid #8ab9b1; }}
    .ghost:hover {{ background: #e3f1ee; }}
    .notice {{ margin: 0 0 14px; padding: 11px 13px; border-left: 4px solid; }}
    .notice.ok {{ background: #e7f4ef; border-color: var(--accent); }}
    .notice.error {{ background: #fbeceb; border-color: var(--danger); color: #762b28; white-space: pre-wrap; }}
    .chat-panel {{ display: grid; gap: 12px; }}
    .chat-log {{ height: clamp(280px, 42vh, 520px); overflow-y: auto; overscroll-behavior: contain; background: var(--soft); border: 1px solid var(--line); padding: 12px; }}
    .chat-message {{ margin: 0 0 10px; padding: 9px 10px; background: white; border-left: 3px solid var(--line); white-space: pre-wrap; }}
    .chat-message.user {{ border-color: #6c9389; }}
    .chat-message.ai {{ border-color: var(--accent); }}
    .chat-row {{ display: grid; gap: 8px; }}
    .chat-input {{ min-height: 110px; font-family: inherit; }}
    .chat-actions {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }}
    .chat-buttons {{ display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }}
    .key-grid {{ display: grid; grid-template-columns: 1fr; gap: 8px; }}
    .hint {{ margin: 0; color: var(--muted); font-size: 13px; }}
    .status {{ min-height: 1.5em; color: var(--accent-dark); }}
    .status.error {{ color: var(--danger); white-space: pre-wrap; }}
    .bottom {{ display: flex; align-items: end; justify-content: space-between; gap: 18px; margin-top: 14px; }}
    .filename {{ flex: 1; max-width: 420px; }}
    .actions {{ display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }}
    .clipboard-result, .mapping-summary {{ margin: 0 0 16px; }}
    .mapping-summary h3 {{ margin: 12px 0 6px; font-size: 15px; }}
    .mapping-summary ul {{ margin: 0; padding-left: 18px; }}
    .mapping-summary li {{ margin: 4px 0; }}
    .clipboard-item {{ min-height: 44px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 8px 0; border-top: 1px solid var(--line); }}
    .clipboard-item:first-of-type {{ border-top: 0; }}
    .clipboard-item button {{ flex: none; padding: 8px 12px; }}
    .xml-source {{ position: fixed; width: 1px; height: 1px; min-height: 1px; opacity: 0; pointer-events: none; }}
    .copy-status {{ min-height: 1.5em; margin: 8px 0 0; color: var(--accent-dark); }}
    a {{ color: var(--accent-dark); font-weight: 650; }}
    @media (max-width: 860px) {{
      main {{ width: min(100% - 20px, 1240px); margin-top: 18px; }}
      header, .bottom {{ display: block; }}
      header p {{ margin-top: 6px; }}
      .layout {{ grid-template-columns: 1fr; }}
      .filename {{ max-width: none; margin-bottom: 12px; }}
      .actions button, .chat-actions button {{ width: 100%; }}
      textarea {{ min-height: 46vh; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Spark AI Python 转积木</h1>
        <p>和 AI 对话生成代码，或直接粘贴 Spark AI Python 生成 XML / .sparkai</p>
      </div>
      <p>{html.escape(api_key_hint)}</p>
    </header>
    {notice}
    <div class="layout">
      <section class="chat-panel">
        <h2>AI 对话</h2>
        <div id="chat-log" class="chat-log" aria-live="polite"></div>
        <div class="key-grid">
          <label for="api-key">DeepSeek Key（可选）</label>
          <input id="api-key" type="password" autocomplete="off" placeholder="已配置默认 Key 时可留空">
          <p class="hint">Key 只发送给本机 127.0.0.1 服务，不会保存到文件。</p>
        </div>
        <div class="chat-row">
          <label for="chat-input">需求描述</label>
          <textarea id="chat-input" class="chat-input" placeholder="例如：生成一个巡线小车，左右电机接 E/F，左右灰度接 A/B，按 A 口触碰传感器停止，停止后蜂鸣器响一声。"></textarea>
        </div>
        <div class="chat-actions">
          <span id="chat-status" class="status"></span>
          <div class="chat-buttons">
            <button id="clear-chat" class="ghost" type="button">清空对话</button>
            <button id="send-chat" type="button">发送给 AI</button>
          </div>
        </div>
      </section>

      <div>
        {mapping_result}
        {clipboard_result}
        <form method="post" action="/generate">
          <h2>候选 Python</h2>
          <label for="python">Python 代码</label>
          <textarea id="python" name="python" spellcheck="false" placeholder="AI 生成的代码会出现在这里，也可以手动粘贴 Spark AI 右侧完整 Python 代码。">{html.escape(source)}</textarea>
          <div class="bottom">
            <div class="filename">
              <label for="filename">文件名（可选）</label>
              <input id="filename" name="filename" value="" placeholder="自动生成时间文件名.sparkai" maxlength="80">
            </div>
            <div class="actions">
              <button type="submit" name="action" value="clipboard" class="secondary">生成剪贴板 XML</button>
              <button type="submit" name="action" value="file">生成积木文件</button>
            </div>
          </div>
        </form>
      </div>
    </div>
  </main>
  <script>
    const chatLog = document.getElementById('chat-log');
    const chatInput = document.getElementById('chat-input');
    const chatStatus = document.getElementById('chat-status');
    const sendChat = document.getElementById('send-chat');
    const clearChat = document.getElementById('clear-chat');
    const pythonArea = document.getElementById('python');
    const apiKeyInput = document.getElementById('api-key');
    const CHAT_STORAGE_KEY = 'sparkai.chatHistory.v1';
    let chatHistory = loadChatHistory();

    function loadChatHistory() {{
      try {{
        const raw = window.localStorage.getItem(CHAT_STORAGE_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return [];
        return parsed
          .filter((item) => item && (item.role === 'user' || item.role === 'ai') && typeof item.text === 'string')
          .slice(-80);
      }} catch (error) {{
        return [];
      }}
    }}

    function saveChatHistory() {{
      try {{
        window.localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(chatHistory));
      }} catch (error) {{
      }}
    }}

    function appendMessage(kind, text) {{
      const item = document.createElement('div');
      item.className = 'chat-message ' + kind;
      item.textContent = text;
      chatLog.appendChild(item);
      chatLog.scrollTop = chatLog.scrollHeight;
    }}

    function renderChatHistory() {{
      chatLog.replaceChildren();
      chatHistory.forEach((item) => appendMessage(item.role, item.text));
      chatLog.scrollTop = chatLog.scrollHeight;
    }}

    function addMessage(kind, text) {{
      chatHistory.push({{ role: kind, text }});
      if (chatHistory.length > 80) chatHistory = chatHistory.slice(-80);
      saveChatHistory();
      appendMessage(kind, text);
    }}

    function buildSummary() {{
      return chatHistory.map((item) => item.role + ': ' + item.text).join('\\n');
    }}

    async function writeClipboard(text) {{
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        await navigator.clipboard.writeText(text);
        return;
      }}
      const fallback = document.createElement('textarea');
      fallback.value = text;
      fallback.style.position = 'fixed';
      fallback.style.opacity = '0';
      document.body.appendChild(fallback);
      fallback.select();
      const copied = document.execCommand('copy');
      fallback.remove();
      if (!copied) throw new Error('clipboard write failed');
    }}

    document.querySelectorAll('[data-copy-target]').forEach((button) => {{
      button.addEventListener('click', async () => {{
        const source = document.getElementById(button.dataset.copyTarget);
        const status = document.getElementById('copy-status');
        try {{
          await writeClipboard(source.value);
          status.textContent = button.parentElement.querySelector('span').textContent + ' 已复制';
        }} catch (error) {{
          status.textContent = '复制失败，请允许浏览器访问剪贴板';
        }}
      }});
    }});

    clearChat.addEventListener('click', () => {{
      chatHistory = [];
      saveChatHistory();
      renderChatHistory();
      chatStatus.className = 'status';
      chatStatus.textContent = '对话已清空';
    }});

    renderChatHistory();

    sendChat.addEventListener('click', async () => {{
      const request = chatInput.value.trim();
      if (!request) return;
      const conversationSummary = buildSummary();
      addMessage('user', request);
      chatInput.value = '';
      sendChat.disabled = true;
      chatStatus.className = 'status';
      chatStatus.textContent = 'AI 正在生成并校验...';
      try {{
        const response = await fetch('/chat', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{
            message: request,
            api_key: apiKeyInput.value,
            conversation_summary: conversationSummary,
            current_python: pythonArea.value
          }})
        }});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'AI 请求失败');
        const responseData = data.response || {{}};
        const lines = [];
        if (responseData.message) lines.push(responseData.message);
        if (responseData.questions && responseData.questions.length) {{
          lines.push('需要确认：');
          responseData.questions.forEach((question) => lines.push('- ' + question));
        }}
        if (responseData.python) {{
          pythonArea.value = responseData.python;
        }}
        if (data.validated) {{
          lines.push('代码已通过本地生成器校验。');
        }} else if (data.validation_error) {{
          lines.push('本地校验未通过：' + data.validation_error);
        }}
        if (typeof data.repair_attempts === 'number' && data.repair_attempts > 0) {{
          lines.push('自动修复次数：' + data.repair_attempts);
        }}
        addMessage('ai', lines.join('\\n') || 'AI 已返回。');
        chatStatus.textContent = data.validated ? '已生成可转换代码' : 'AI 已回复';
      }} catch (error) {{
        chatStatus.className = 'status error';
        chatStatus.textContent = error.message;
        addMessage('ai', '出错：' + error.message);
      }} finally {{
        sendChat.disabled = false;
      }}
    }});
  </script>
</body>
</html>"""
    return document.encode("utf-8")


def json_response(handler: SimpleHTTPRequestHandler, payload: dict[str, object], status: int = 200) -> None:
    content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


class SparkAIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def respond_html(self, content: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON request: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON request must be an object")
        return data

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html", "/generate"}:
            self.respond_html(page())
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/chat":
            self.handle_chat()
            return
        if path == "/generate":
            self.handle_generate()
            return
        self.send_error(404)

    def handle_chat(self) -> None:
        try:
            data = self.read_json()
            message = str(data.get("message", "")).strip()
            if not message:
                raise SparkAIAIError("用户需求不能为空")
            api_key = resolve_api_key(str(data.get("api_key", "")))
            conversation_summary = str(data.get("conversation_summary", "")).strip()
            current_python = str(data.get("current_python", ""))
            project_state = json.dumps(
                {
                    "has_current_python": bool(current_python.strip()),
                    "current_python": current_python,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            result = generate_with_deepseek(
                message,
                api_key=api_key,
                project_state=project_state,
                conversation_summary=conversation_summary,
            )
            json_response(
                self,
                {
                    "validated": result.validated,
                    "validation_error": result.validation_error,
                    "repair_attempts": result.repair_attempts,
                    "response": result.response.raw,
                },
            )
        except (OSError, ValueError, SparkAIAIError) as exc:
            json_response(self, {"error": str(exc)}, 400)

    def handle_generate(self) -> None:
        source = ""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            source = form.get("python", [""])[0]
            if not source.strip():
                raise ReverseCodeError("Python input is empty")
            action = form.get("action", ["file"])[0]
            if action == "clipboard":
                result = compile_clipboard(source)
                message = f"已生成 {len(result.fragments)} 段剪贴板 XML"
                self.respond_html(
                    page(
                        message=message,
                        source=source,
                        fragments=result.fragments,
                        mapping_report=result.mapping_report,
                    )
                )
                return
            if action != "file":
                raise ReverseCodeError(f"unknown generation action: {action}")
            filename = form.get("filename", [""])[0].strip()
            if filename:
                filename = Path(filename).name
                if not filename.lower().endswith(".sparkai"):
                    filename += ".sparkai"
                output = OUTPUT_DIR / filename
            else:
                output = unique_output_path(OUTPUT_DIR)
            result = compile_project(source, TEMPLATE, output)
            link = f"/generated/{result.path.name}"
            message = (
                f'生成成功：<a href="{html.escape(link)}">下载 {html.escape(result.path.name)}</a>'
                f"（{result.block_count} 个积木节点）"
            )
            self.respond_html(
                page(
                    message=message,
                    source=source,
                    mapping_report=result.mapping_report,
                )
            )
        except (OSError, ValueError) as exc:
            self.respond_html(page(message=str(exc), error=True, source=source), 400)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        server = ThreadingHTTPServer((args.host, args.port), SparkAIHandler)
    except OSError as exc:
        print(f"ERROR: cannot start server on {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 2
    print(f"Spark AI generator: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
