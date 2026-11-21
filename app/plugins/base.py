from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel


class BasePlugin(ABC):
    name: str
    category: str
    description: str
    input_schema: type[BaseModel]

    def validate_params(self, params: dict[str, Any]) -> BaseModel:
        return self.input_schema(**(params or {}))

    @abstractmethod
    def execute(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute plugin logic.
        `params` are validated inputs.
        `context` is the shared runtime execution context.
        Returns a dictionary of execution results.
        """
        raise NotImplementedError
