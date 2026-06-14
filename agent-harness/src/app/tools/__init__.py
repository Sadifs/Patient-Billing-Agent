"""Tool registry.

Import your tools here and add them to the TOOLS list.
The server registers all tools in this list with the agent harness.

HOW TO ADD A TOOL:
    1. Create a new file in tools/, e.g. tools/my_tool.py
    2. Define your function with the @tool decorator:

        from agent_harness import tool
        import json

        @tool(name="my_tool", description="...", parameters={
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "..."},
            },
            "required": ["param1"],
        })
        def my_tool(args: dict) -> str:
            # Your implementation here
            return json.dumps({"result": "..."})

    3. Import it here and add it to the TOOLS list.

    For tools that need external state (DB connections, API clients),
    use the create_tool() factory pattern — see search_bills.py for an example.
"""

# from app.tools.your_tool import your_tool

from app.tools.calculate_fpl import calculate_fpl

TOOLS = [
    calculate_fpl,
]
