import inspect
from typing import Callable


class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, name: str, description: str, func: Callable, schema: dict = None):
        self._tools[name] = {
            "description": description,
            "function": func,
            "schema": schema or {},
        }

    def list_tools(self):
        return [
            {
                "name": name,
                "description": data["description"],
                "params": data["schema"],
            }
            for name, data in self._tools.items()
        ]

    def get(self, name: str):
        return self._tools.get(name)

    async def execute(self, tool_name: str, params: dict):
        tool = self.get(tool_name)

        if not tool:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}

        try:
            func = tool["function"]
            if inspect.iscoroutinefunction(func):
                result = await func(**params)
            else:
                result = func(**params)

            return {"success": True, "result": result}

        except Exception as e:
            return {"success": False, "error": str(e)}


registry = ToolRegistry()