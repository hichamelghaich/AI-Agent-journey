# LESSON 2: Functions
# Run with: python3 functions.py
#
# Why this matters for the agent: every "tool" we give Claude is just a
# Python function. Claude never runs the function itself -- it just asks
# US to run it and tells us what arguments to use. Understanding function
# definitions, parameters, return values, and type hints is what makes
# the tool code readable instead of mysterious.

# A basic function: 'def' defines it, the stuff in () are parameters,
# and 'return' sends a value back to whoever called it.
def add(a, b):
    return a + b

print(add(2, 3))  # 5

# Type hints (the ": int" and "-> int" parts) are optional but very
# useful -- they document what a function expects and returns without
# needing a comment. Python doesn't enforce them strictly, but tools
# (and readers, and Claude) rely on them.
def multiply(a: int, b: int) -> int:
    return a * b

print(multiply(4, 5))  # 20

# A function with a default value for a parameter -- if you don't pass
# 'unit', it falls back to "celsius".
def describe_temp(value: float, unit: str = "celsius") -> str:
    return f"{value} degrees {unit}"

print(describe_temp(20))                  # uses the default
print(describe_temp(68, unit="fahrenheit"))  # overrides it

# Functions that can fail: this is the pattern we use in the agent's
# tools. We catch errors instead of letting the program crash, and
# return a message describing what went wrong.
def safe_divide(a: float, b: float) -> str:
    try:
        return str(a / b)
    except ZeroDivisionError:
        return "Error: cannot divide by zero"

print(safe_divide(10, 2))   # "5.0"
print(safe_divide(10, 0))   # "Error: cannot divide by zero"

# A function can take another function's name and call it dynamically.
# This is EXACTLY how the agent decides which tool to run: it gets a
# tool NAME (a string) from Claude, looks it up in a dict, and calls it.
def square(x):
    return x * x

def cube(x):
    return x ** 3

operations = {
    "square": square,
    "cube": cube,
}

chosen_operation = "cube"   # imagine this string came from Claude
func = operations[chosen_operation]
print(func(3))  # 27 -- we "looked up" cube() by name and called it
