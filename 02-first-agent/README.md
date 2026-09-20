# 02 — First agent (math/utility)

A minimal but real agent: it has three tools (`calculate`, `sqrt`,
`percentage`) and a loop that lets Claude call them as many times as it
needs before answering.

## Concepts introduced here

- **`.env` files + `load_dotenv()`** — keeping the API key out of source
  code and git history entirely.
- **Tool schemas as JSON Schema** — describing a Python function to
  Claude in a language-agnostic format.
- **The `messages` list** — the API has no memory of its own; we resend
  the whole conversation every call.
- **`stop_reason`** — how we know whether Claude wants a tool or is done.
- **`**block.input`** — unpacking a dict into function keyword arguments.

## Run it

```bash
pip install -r requirements.txt --break-system-packages
cp .env.example .env
# edit .env and paste your real ANTHROPIC_API_KEY
python3 agent.py
```

Try: `what's 15% of 340, then take the square root of that` — watch it
chain two tool calls before giving a final answer.
