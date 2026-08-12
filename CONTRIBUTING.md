# Contributing

Contributions are welcome, especially new Spark AI block mappings and regression
samples.

## Before You Start

This project only supports blocks that can be created in the Spark AI UI. When
adding support for a new block, please start from a real Spark AI sample rather
than guessing the block shape.

Useful artifacts:

- Python copied from Spark AI's code panel.
- A `.sparkai` project containing the block.
- Clipboard XML copied from the Spark AI workspace, when available.
- A screenshot of the block if the input controls are unusual.

When adding a supported block, also update
`docs/ai_rules/supported_functions.md` so future AI generation uses the new
function correctly.

## Development Setup

No third-party dependencies are required.

```powershell
python -m unittest discover -s tools -p "test_*.py"
```

AI API tests that call a real provider should be run manually with an
environment variable and should not commit keys:

```powershell
$env:DEEPSEEK_API_KEY = "your-api-key"
python tools\sparkai_ai.py generate "生成一个巡线小车"
```

Run the web UI:

```powershell
.\Start-SparkAI-Generator.cmd
```

Or run the Python server directly:

```powershell
python tools\sparkai_web.py --host 127.0.0.1 --port 8765
```

## Adding A Block

1. Add or update a minimal example.
2. Implement the compiler behavior in `tools/sparkai_reverse.py`.
3. Add validation for UI-sensitive inputs in `validate_generated_inputs()`.
4. Update clipboard XML handling only if the block uses a new primitive shape.
5. Add tests in `tools/test_sparkai_reverse.py` or
   `tools/test_sparkai_clipboard.py`.
6. Run the full test suite.

## Pull Request Checklist

- The new behavior is based on a real Spark AI block.
- Unsupported or ambiguous input still fails loudly.
- Public examples do not require local `work/`, `generated/` or `outputs/`
  files.
- Tests pass with:

```powershell
python -m unittest discover -s tools -p "test_*.py"
```
