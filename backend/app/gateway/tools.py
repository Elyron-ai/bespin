"""Tool registry for the Tool Invocation Gateway."""
from typing import Any, Callable


class ToolNotFoundError(Exception):
    """Raised when a requested tool is not found in the registry."""
    pass


class ToolRegistry:
    """In-process registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}

    def register(
        self, name: str
    ) -> Callable[[Callable[[dict[str, Any]], dict[str, Any]]], Callable[[dict[str, Any]], dict[str, Any]]]:
        """Decorator to register a tool.

        Args:
            name: The name of the tool.

        Returns:
            A decorator function.
        """
        def decorator(
            func: Callable[[dict[str, Any]], dict[str, Any]]
        ) -> Callable[[dict[str, Any]], dict[str, Any]]:
            self._tools[name] = func
            return func
        return decorator

    def invoke(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke a registered tool.

        Args:
            name: The name of the tool to invoke.
            payload: The payload to pass to the tool.

        Returns:
            The tool's output.

        Raises:
            ToolNotFoundError: If the tool is not registered.
        """
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool '{name}' not found")
        return self._tools[name](payload)

    def list_tools(self) -> list[str]:
        """List all registered tool names.

        Returns:
            A list of tool names.
        """
        return list(self._tools.keys())


# Global registry instance
registry = ToolRegistry()


@registry.register("echo")
def echo_tool(payload: dict[str, Any]) -> dict[str, Any]:
    """Echo tool - returns the payload wrapped in an 'echo' key.

    Args:
        payload: Any dictionary payload.

    Returns:
        The payload echoed back.
    """
    return {"echo": payload}
