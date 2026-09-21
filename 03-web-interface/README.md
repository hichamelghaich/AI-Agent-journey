# 03 — Web interface

The same agent as `02-first-agent`, running in a browser instead of a
terminal, and with conversation memory added.

## What changed

**Gradio replaces the terminal loop.** `gr.ChatInterface` takes a single
function and generates the whole page — input box, message history,
example prompts, and a local web server to serve it.

**The agent now remembers.** In 02, every question started with an empty
`messages` list, so it had no idea what you'd asked before. Here Gradio
passes the previous turns in, and they go at the front of the list. That
is all "memory" is with an LLM API: the model itself stores nothing, so
the past gets resent every time.

**Tool calls are visible in the UI.** Each answer is prefixed with the
tools that were called and what they returned — the same trace that was
printed to the terminal in 02.

The tools and the agent loop are otherwise identical. The interface and
the agent logic are independent of each other, which is the point.

## Run it

```bash
py -m pip install -r requirements.txt
copy .env.example .env      # then paste your key into .env
py app.py
```

Open the `http://127.0.0.1:7860` link it prints. Ctrl+C in the terminal
stops the server.

Try asking a follow-up like "now double that" to see the memory working.
