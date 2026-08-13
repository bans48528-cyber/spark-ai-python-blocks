# AI 提示词模板

这些模板供本地后端调用 AI API 时使用，不直接展示给最终用户。

## 生成代码请求

系统/开发者内容：

```text
阅读并遵守 ai_generation_rules.md、hardware_overview.md、
conversation_state.md、block_semantics.md、supported_functions.md
和 supported_blocks.md。
只返回 JSON。
```

后端组装的用户内容：

```text
项目状态：
{project_state_json}

对话摘要：
{conversation_summary}

用户最新请求：
{latest_user_message}

生成 Spark AI Python，或提出需要澄清的问题。
```

期望响应：

```json
{
  "type": "code",
  "message": "中文说明",
  "python": "完整 Spark AI Python",
  "assumptions": [],
  "needs_clarification": false,
  "questions": [],
  "hardware_config": {}
}
```

## 修复代码请求

系统/开发者内容：

```text
阅读并遵守 ai_generation_rules.md、hardware_overview.md、
conversation_state.md、block_semantics.md、supported_functions.md
和 supported_blocks.md。
只返回 JSON。
你正在修复一段未通过本地转换器校验的代码。
```

后端组装的用户内容：

```text
用户原始请求：
{original_user_request}

项目状态：
{project_state_json}

转换器校验错误：
{converter_error}

失败的 Python：
{failed_python}

返回完整修正后的 JSON 响应。保持支持范围内的行为和映射关系。
```

## 澄清响应处理

如果 AI 返回 `"type": "question"`，后端应向用户显示 `message` 和 `questions`，不要调用转换器。

如果 AI 返回 `"type": "code"`，后端应提取 `python` 字段，并运行：

```python
SparkAIReverseCompiler().compile(python_code)
```

如果校验成功，将代码显示为候选版本。如果校验失败，进入修复流程，修复次数使用一个较小固定上限，例如 2 次。

## 后端上下文策略

第一版保持简单：

- 每次都携带 `ai_generation_rules.md`。
- 每次都携带 `hardware_overview.md`。
- 每次都携带 `block_semantics.md`。
- 代码生成或修复请求中携带 `supported_functions.md`。
- 代码生成或修复请求中携带 `supported_blocks.md`。
- 只有在确实有帮助时，最多携带一个短示例。
- 对话变长后，不要携带完整原始聊天历史。只携带紧凑摘要或最近少量轮次，避免把 AI 旧回答和旧问题反复送回模型。
- 维护一个紧凑的项目状态 JSON，记录已选择端口、行为选项和最新接受的代码版本。

对于较短的多轮会话，直接携带这些规则文件通常仍在常见模型上下文范围内。
