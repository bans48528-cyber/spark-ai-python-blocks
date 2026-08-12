# AI Prompt Templates

These templates are for the local backend when calling an AI API. They are not
shown to end users.

## Generate Code Request

System/developer content:

```text
Read and follow ai_generation_rules.md, hardware_overview.md,
block_semantics.md and supported_functions.md.
Return JSON only.
```

User content assembled by the backend:

```text
Project state:
{project_state_json}

Conversation summary:
{conversation_summary}

User request:
{latest_user_message}

Generate Spark AI Python or ask clarification questions.
```

Expected response:

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

## Repair Code Request

System/developer content:

```text
Read and follow ai_generation_rules.md, hardware_overview.md,
block_semantics.md and supported_functions.md.
Return JSON only.
You are repairing code that failed local converter validation.
```

User content assembled by the backend:

```text
Original user request:
{original_user_request}

Project state:
{project_state_json}

Validation error:
{converter_error}

Failed Python:
{failed_python}

Return a full corrected JSON response. Keep supported behavior and mappings.
```

## Clarification Response Handling

If the AI returns `"type": "question"`, the backend should display
`message` and `questions` to the user and should not call the converter.

If the AI returns `"type": "code"`, the backend should extract `python` and
run:

```python
SparkAIReverseCompiler().compile(python_code)
```

If validation succeeds, show the code as a candidate version. If validation
fails, run the repair flow up to a small fixed limit, such as 2 attempts.

## Backend Context Strategy

Keep this simple at first:

- Always include `ai_generation_rules.md`.
- Always include `hardware_overview.md`.
- Always include `block_semantics.md`.
- Always include `supported_functions.md`.
- Include at most one short example only if needed.
- Do not include the full raw chat history after it becomes long.
- Maintain a compact project-state JSON with selected ports, behavior choices
  and the latest accepted code version.

For a short multi-turn session, including the rule files directly should be
well within common model context limits.
