# Tools

This directory contains the Python tools for Spark AI Python to Blocks.

Most users should start with the repository root [README.md](../README.md).
Developers extending block support should also read
[DEVELOPMENT.md](../DEVELOPMENT.md).

## Entry Points

- `sparkai_web.py`: local browser UI for pasting Python and generating output.
- `sparkai_tool.py`: CLI for inspect, validate, compare and `.sparkai` output.
- `sparkai_reverse.py`: reverse compiler from Spark AI Python to block graph.
- `sparkai_clipboard.py`: serializer from block graph to pasteable Blockly XML.
- `sparkai_ai.py`: experimental DeepSeek-compatible AI generation smoke test.

## Quick Commands

Run tests:

```powershell
python -m unittest discover -s tools -p "test_*.py"
```

Start the web UI:

```powershell
..\Start-SparkAI-Generator.cmd
```

Or start it manually from the repository root:

```powershell
python tools\sparkai_web.py --host 127.0.0.1 --port 8765
```

Generate a `.sparkai` file:

```powershell
python tools\sparkai_tool.py generate examples\line_follower.py --output generated\line_follower.sparkai
```
