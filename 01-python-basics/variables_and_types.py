# LESSON 1: Variables and basic types
# Run this file with: python3 lesson1_basics.py

# A variable is just a name pointing at a value. No need to declare a type.
name = "icham"          # str (text)
age = 5                 # int (whole number)
price = 3.50             # float (decimal number)
is_learning = True       # bool (True/False)

print(name)
print(age)
print(price)
print(is_learning)

# f-strings: the standard way to build text with variables inside it.
# Anything inside {} gets evaluated and inserted.
print(f"{name} has been learning for {age} days")

# A list: an ordered, changeable collection.
tools = ["calculate", "sqrt", "percentage"]
print(tools)
print(tools[0])      # first item -- Python counts from 0
print(len(tools))    # how many items

# A dict (dictionary): key -> value pairs. This is CRITICAL for the agent
# code, because tool schemas and API messages are all dicts.
tool_info = {
    "name": "calculate",
    "description": "Evaluates arithmetic",
    "max_tokens": 1024,
}
print(tool_info["name"])          # access by key
print(tool_info.get("missing"))   # .get() returns None instead of erroring

# type() tells you what kind of thing a variable is -- useful for debugging.
print(type(name), type(age), type(tools), type(tool_info))
