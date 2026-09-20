# AI Agent Journey

My learning log for understanding AI agents, LLMs, and Python (and whatever
other languages come up along the way) — built as a series of small,
working projects instead of tutorials I'd forget.

Each numbered folder is a step. The commit history is part of the
learning material: read it top to bottom and it tells the story of how
each project grew, one concept at a time.

## Roadmap

- [x] `01-python-basics` — variables, functions, dicts: the Python I need
      before touching the agent code
- [x] `02-first-agent` — a math/utility agent using the Claude API and
      tool calling
- [ ] more to come...

## Running things

Each folder has its own instructions in its README. In general:

```bash
pip install -r requirements.txt --break-system-packages
export ANTHROPIC_API_KEY="sk-ant-..."
python3 <script>.py
```

Never commit an actual API key. Keys are always read from an environment
variable, never hardcoded in a file.
