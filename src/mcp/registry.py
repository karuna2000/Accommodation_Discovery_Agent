from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.mcp.tools.base import BaseTool, ToolDependencies


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, type] = {}

    def register(self, tool_cls: type) -> type:
        name = getattr(tool_cls, "name", None)
        if not name:
            msg = f"Tool {tool_cls.__name__} must have a `name` attribute"
            raise ValueError(msg)
        self._tools[name] = tool_cls
        return tool_cls

    def create_all(self, deps: ToolDependencies) -> dict[str, BaseTool]:
        instances: dict[str, BaseTool] = {}
        for name, cls in self._tools.items():
            instances[name] = cls(deps)
        return instances

    def get_schemas(self) -> list[dict]:
        schemas = []
        for name, cls in self._tools.items():
            schemas.append({
                "name": name,
                "description": getattr(cls, "description", ""),
                "input_schema": getattr(cls, "input_schema", {}),
            })
        return schemas

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())


registry = ToolRegistry()


def tool(cls: type) -> type:
    registry.register(cls)
    return cls
