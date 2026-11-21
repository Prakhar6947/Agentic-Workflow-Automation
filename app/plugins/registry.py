from typing import Any
from app.plugins.base import BasePlugin


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, BasePlugin] = {}

    def register(self, cls: type[BasePlugin]) -> type[BasePlugin]:
        inst = cls()
        self._plugins[inst.name] = inst
        return cls

    def get(self, name: str) -> BasePlugin | None:
        return self._plugins.get(name)

    def list_plugins(self) -> list[dict[str, Any]]:
        return [
            {
                "name": p.name,
                "category": p.category,
                "description": p.description,
                "schema": p.input_schema.model_json_schema(),
            }
            for p in self._plugins.values()
        ]


registry = PluginRegistry()
