"""
03-web-interface: the same agent, but with a browser UI instead of a terminal.

Two things change from 02-first-agent:

  1. Gradio provides the interface. It's a Python library that builds a web
     page for you -- you describe the inputs and outputs, it handles the
     HTML, CSS, JavaScript and the little web server underneath.

  2. The agent now has MEMORY. In 02 each question started from scratch.
     Here we pass the previous conversation back in every time, so you can
     say "now double that" and it knows what "that" refers to.

Run it:
    py -m pip install -r requirements.txt
    py app.py

Then open the http://127.0.0.1:7860 link it prints.
"""

import math
import gradio as gr
from dotenv import load_dotenv
import anthropic

load_dotenv()

client = anthropic.Anthropic()
MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# TOOLS -- unchanged from 02. The agent's "brain" doesn't care what
# interface is in front of it. That separation is the point.
# ---------------------------------------------------------------------------

def calculate(expression: str) -> str:
    allowed = "0123456789+-*/(). %"
    if not all(c in allowed for c in expression):
        return "Error: expression contains disallowed characters."
    try:
        return str(eval(expression, {"__builtins__": {}}))
    except Exception as e:
        return f"Error: {e}"


def sqrt(number: float) -> str:
    try:
        return str(math.sqrt(number))
    except Exception as e:
        return f"Error: {e}"


def percentage(part: float, whole: float) -> str:
    try:
        return f"{(part / whole) * 100}%"
    except Exception as e:
        return f"Error: {e}"


TOOL_FUNCTIONS = {
    "calculate": calculate,
    "sqrt": sqrt,
    "percentage": percentage,
}

TOOL_SCHEMAS = [
    {
        "name": "calculate",
        "description": "Evaluate a basic arithmetic expression, e.g. '12 * (3 + 4)'. Supports + - * / % and parentheses.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "The arithmetic expression to evaluate"}
            },
            "required": ["expression"],
        },
    },
    {
        "name": "sqrt",
        "description": "Compute the square root of a single number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "number": {"type": "number", "description": "The number to take the square root of"}
            },
            "required": ["number"],
        },
    },
    {
        "name": "percentage",
        "description": "Compute what percent 'part' is of 'whole'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "part": {"type": "number"},
                "whole": {"type": "number"},
            },
            "required": ["part", "whole"],
        },
    },
]

SYSTEM_PROMPT = (
    "You are a careful math assistant. For any arithmetic, square roots, or "
    "percentage question, ALWAYS use the provided tools to compute the exact "
    "answer instead of calculating it yourself in your head. Keep answers short."
)


# ---------------------------------------------------------------------------
# THE AGENT LOOP
#
# New parameter: 'history'. Gradio hands us the previous turns of the
# conversation, and we put them at the front of the messages list. That is
# ALL that "memory" means here -- we resend the past every time.
# ---------------------------------------------------------------------------

def run_agent(user_message: str, history: list) -> str:
    # Rebuild the conversation: old turns first, then the new question.
    # Gradio may hand us dicts or small objects, so read both shapes.
    messages = []
    for turn in history:
        if isinstance(turn, dict):
            role, content = turn.get("role"), turn.get("content")
        else:
            role, content = getattr(turn, "role", None), getattr(turn, "content", None)
        if role in ("user", "assistant") and isinstance(content, str) and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    # We collect a log of tool calls so the UI can show its work.
    tool_log = []

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            answer = "".join(b.text for b in response.content if b.type == "text")
            if tool_log:
                # Show the tool calls above the answer, in small grey text.
                trace = "\n".join(f"`{line}`" for line in tool_log)
                return f"{trace}\n\n{answer}"
            return answer

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            func = TOOL_FUNCTIONS[block.name]
            result = func(**block.input)
            tool_log.append(f"{block.name}({block.input}) -> {result}")
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }
            )

        messages.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# THE INTERFACE
#
# ChatInterface builds an entire chat page from one function. It expects a
# function taking (message, history) and returning a string -- which is
# exactly the shape of run_agent above.
# ---------------------------------------------------------------------------

demo = gr.ChatInterface(
    fn=run_agent,
    title="Math Agent",
    description=(
        "An AI agent with three real tools. Ask in plain language — it "
        "decides which tool to call and shows its work."
    ),
    examples=[
        "what's 15% of 340, then the square root of that",
        "862000 times 12,5",
        "what is 2847 * 391?",
    ],
)

if __name__ == "__main__":
    demo.launch()
