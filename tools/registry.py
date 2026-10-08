"""
Tool Registry for NexaOps.
Stores tool definitions, input schemas (Pydantic), and metadata (read_only, retryable).
Provides catalog generation for LLM system prompts.
"""

from typing import Callable, Dict, Any, Type, Optional, List
from pydantic import BaseModel


class ToolDefinition:
    """Metadata and execution wrapper for an agent tool."""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Type[BaseModel],
        func: Callable[..., Dict[str, Any]],
        read_only: bool = True,
        retryable: bool = False
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.func = func
        self.read_only = read_only
        self.retryable = retryable

    def get_catalog_entry(self) -> Dict[str, Any]:
        """Returns JSON schema representation of the tool for LLM prompting."""
        schema = self.input_schema.model_json_schema()
        # Extract properties and required fields
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        return {
            "name": self.name,
            "description": self.description,
            "parameters": properties,
            "required": required,
            "read_only": self.read_only,
            "retryable": self.retryable
        }


class ToolRegistry:
    """Central registry of all tools available to the NexaOps agent."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Type[BaseModel],
        read_only: bool = True,
        retryable: bool = False
    ) -> Callable[[Callable], Callable]:
        """Decorator to register a tool with its schema and metadata."""
        def decorator(func: Callable) -> Callable:
            tool_def = ToolDefinition(
                name=name,
                description=description,
                input_schema=input_schema,
                func=func,
                read_only=read_only,
                retryable=retryable
            )
            self._tools[name] = tool_def
            return func
        return decorator

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Retrieves a tool definition by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        """Returns all registered tool definitions."""
        return list(self._tools.values())

    def get_catalog_for_prompt(self) -> List[Dict[str, Any]]:
        """Returns a simplified catalog list for inclusion in LLM prompts."""
        return [tool.get_catalog_entry() for tool in self._tools.values()]


# Global registry singleton
registry = ToolRegistry()
