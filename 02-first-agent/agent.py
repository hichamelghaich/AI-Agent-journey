"""
02-first-agent: a math/utility agent using the Claude API.

CONCEPT: what makes this an "agent" and not just a chatbot call
------------------------------------------------------------------
A plain chatbot call is one request, one response. An agent adds a LOOP:

    ask Claude -> does it want a tool? -> run the tool in real Python
    -> send the result back to Claude -> ask again -> ... -> final answer

Claude decides WHEN and WHICH tool to use. We never hardcode
"if user says X, call Y" -- that decision-making is the whole point.

Run it:
    pip install -r requirements.txt --break-system-packages
    cp .env.example .env      # then edit .env and paste your real key
    python3 agent.py
"""

import os
import math
from dotenv import load_dotenv
import anthropic

# CONCEPT: environment variables + .env files
# We NEVER hardcode an API key in source code (it'd end up in git history
# forever, even if you delete it later). Instead, load_dotenv() reads a
# local .env file (which is gitignored -- see .gitignore) and puts its
# contents into os.environ, where the anthropic client looks for the key
# automatically.
load_dotenv()

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

# Model IDs change over time -- check platform.claude.com/docs for current
# ones. Haiku is the cheapest and is plenty for simple tool calling, so
# it's a good default while learning. Swap to claude-sonnet-5 for harder
# reasoning.
MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# 1. THE TOOLS
# Plain Python functions. Nothing about them is special or magic -- you
# could call calculate("2+2") yourself right now and it would just work.
# ---------------------------------------------------------------------------

def calculate(expression: str) -> str:
    """Safely evaluate a basic arithmetic expression."""
    allowed = "0123456789+-*/(). %"
    if not all(c in allowed for c in expression):
        return "Error: expression contains disallowed characters."
    try:
        result = eval(expression, {"__builtins__": {}})
        return str(result)
    except Exception as e:
        return f"Error: {e}"


def sqrt(number: float) -> str:
    """Square root of a number."""
    try:
        return str(math.sqrt(number))
    except Exception as e:
        return f"Error: {e}"


def percentage(part: float, whole: float) -> str:
    """What percent 'part' is of 'whole'."""
    try:
        return f"{(part / whole) * 100}%"
    except Exception as e:
        return f"Error: {e}"


# CONCEPT: this is the name -> function dict pattern from 01-python-basics.
# Claude will tell us a tool NAME as a string (e.g. "sqrt"). We use that
# string to look up and call the real function.
TOOL_FUNCTIONS = {
    "calculate": calculate,
    "sqrt": sqrt,
    "percentage": percentage,
}

# CONCEPT: tool schemas are JSON (in Python, a dict/list of dicts).
# This is how we describe our Python functions to Claude in a format it
# can read. Claude never sees our Python code -- only this description.
# "input_schema" follows JSON Schema, a standard for describing the shape
# of data (used everywhere: APIs, config validation, forms).
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
    "answer instead of calculating it yourself in your head. Explain the "
    "result briefly once you have it."
)


# ---------------------------------------------------------------------------
# 2. THE AGENT LOOP
# ---------------------------------------------------------------------------

def run_agent(user_message: str) -> str:
    # CONCEPT: 'messages' is the entire conversation history, as a list of
    # dicts. Every API call sends the WHOLE list -- the API itself has no
    # memory between calls. We are responsible for remembering.
    messages = [{"role": "user", "content": user_message}]

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        # Add Claude's reply to the history so it has context next time.
        messages.append({"role": "assistant", "content": response.content})

        # CONCEPT: stop_reason tells us WHY Claude stopped generating.
        # "tool_use" means "I want to call a tool before I can answer."
        # Anything else means it's done and gave us a final answer.
        if response.stop_reason != "tool_use":
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            )
            return final_text

        # Claude wants tool(s). response.content is a list of "blocks" --
        # could be text explaining its plan AND one or more tool_use blocks.
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            func = TOOL_FUNCTIONS[block.name]
            print(f"  -> agent is calling tool: {block.name}({block.input})")
            # block.input is a dict of arguments, e.g. {"number": 16}
            # **block.input "unpacks" that dict into keyword arguments:
            # func(**{"number": 16}) is the same as func(number=16)
            result = func(**block.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,  # links this result to that specific call
                    "content": result,
                }
            )

        # Tool results go back in as a "user" turn (from the API's point of
        # view, we're the ones handing information back).
        messages.append({"role": "user", "content": tool_results})
        # Loop continues -- Claude sees the result and decides what's next.


# ---------------------------------------------------------------------------
# 3. A SIMPLE CHAT LOOP TO TRY IT OUT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("No API key found. Copy .env.example to .env and add your key.")
        raise SystemExit(1)

    print("Math agent ready. Ask it a question (or type 'quit').\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        answer = run_agent(user_input)
        print(f"Agent: {answer}\n")
