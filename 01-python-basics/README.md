# 01 — Python basics

The minimum Python I need before the agent code makes sense: variables,
types, lists, and dicts.

The big one to internalize: **dicts**. Claude's API sends and receives
everything as nested dicts/JSON — tool definitions, messages, tool
results. If dicts click, the agent code stops looking like magic.

Run it:

```bash
python3 variables_and_types.py
```

## `functions.py`

Functions, type hints, default parameters, and the pattern that makes
agents possible: a dict that maps a tool NAME (a string) to a real
function, looked up and called dynamically. This is exactly how the
agent decides which tool to run based on what Claude asks for.

```bash
python3 functions.py
```
