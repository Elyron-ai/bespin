"""Tool registry for the Tool Invocation Gateway."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session


@dataclass
class ToolContext:
    """Context passed to context-aware tools."""
    tenant_id: str
    db: Session


class ToolNotFoundError(Exception):
    """Raised when a requested tool is not found in the registry."""
    pass


# Type aliases for tool functions
SimpleToolFunc = Callable[[dict[str, Any]], dict[str, Any]]
ContextToolFunc = Callable[[dict[str, Any], ToolContext], dict[str, Any]]


class ToolRegistry:
    """In-process registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, SimpleToolFunc] = {}
        self._context_tools: dict[str, ContextToolFunc] = {}

    def register(
        self, name: str
    ) -> Callable[[SimpleToolFunc], SimpleToolFunc]:
        """Decorator to register a simple tool (no context needed).

        Args:
            name: The name of the tool.

        Returns:
            A decorator function.
        """
        def decorator(func: SimpleToolFunc) -> SimpleToolFunc:
            self._tools[name] = func
            return func
        return decorator

    def register_context_tool(
        self, name: str
    ) -> Callable[[ContextToolFunc], ContextToolFunc]:
        """Decorator to register a context-aware tool (needs db/tenant access).

        Args:
            name: The name of the tool.

        Returns:
            A decorator function.
        """
        def decorator(func: ContextToolFunc) -> ContextToolFunc:
            self._context_tools[name] = func
            return func
        return decorator

    def invoke(
        self,
        name: str,
        payload: dict[str, Any],
        context: ToolContext | None = None,
    ) -> dict[str, Any]:
        """Invoke a registered tool.

        Args:
            name: The name of the tool to invoke.
            payload: The payload to pass to the tool.
            context: Optional context for context-aware tools.

        Returns:
            The tool's output.

        Raises:
            ToolNotFoundError: If the tool is not registered.
            ValueError: If a context-aware tool is invoked without context.
        """
        if name in self._tools:
            return self._tools[name](payload)
        if name in self._context_tools:
            if context is None:
                raise ValueError(f"Tool '{name}' requires context but none provided")
            return self._context_tools[name](payload, context)
        raise ToolNotFoundError(f"Tool '{name}' not found")

    def list_tools(self) -> list[str]:
        """List all registered tool names.

        Returns:
            A list of tool names.
        """
        return list(self._tools.keys()) + list(self._context_tools.keys())


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


@registry.register_context_tool("kpi_summary")
def kpi_summary_tool(payload: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """KPI summary tool - computes trend data for a KPI within a time window.

    Args:
        payload: Dict with 'kpi_id' (required) and 'window_days' (default 7).
        context: Tool context with tenant_id and db session.

    Returns:
        Dict with kpi_id, latest, start, delta_abs, and delta_pct.
    """
    # Import here to avoid circular imports
    from app.gateway.models import KPIDefinition, KPIPoint

    kpi_id = payload.get("kpi_id")
    if not kpi_id:
        return {"error": "Missing required field: kpi_id"}

    window_days = payload.get("window_days", 7)
    if not isinstance(window_days, int) or window_days < 1:
        return {"error": "window_days must be a positive integer"}

    # Verify KPI exists and belongs to this tenant
    kpi = context.db.query(KPIDefinition).filter(
        KPIDefinition.kpi_id == kpi_id,
        KPIDefinition.tenant_id == context.tenant_id,
    ).first()
    if not kpi:
        return {"error": f"KPI '{kpi_id}' not found"}

    # Get the latest point
    latest_point = context.db.query(KPIPoint).filter(
        KPIPoint.tenant_id == context.tenant_id,
        KPIPoint.kpi_id == kpi_id,
    ).order_by(KPIPoint.ts.desc()).first()

    if not latest_point:
        return {"error": f"No data points found for KPI '{kpi_id}'"}

    # Parse latest timestamp and compute window start
    latest_ts = datetime.fromisoformat(latest_point.ts.replace("Z", "+00:00"))
    window_start = latest_ts - timedelta(days=window_days)
    window_start_str = window_start.isoformat().replace("+00:00", "Z")

    # Find the earliest point within the window (ts >= window_start AND ts <= latest.ts)
    start_point = context.db.query(KPIPoint).filter(
        KPIPoint.tenant_id == context.tenant_id,
        KPIPoint.kpi_id == kpi_id,
        KPIPoint.ts >= window_start_str,
        KPIPoint.ts <= latest_point.ts,
    ).order_by(KPIPoint.ts.asc()).first()

    # If no start point found within window, use latest as start (edge case)
    if not start_point:
        start_point = latest_point

    # Calculate deltas
    delta_abs = latest_point.value - start_point.value
    if start_point.value == 0:
        delta_pct = None
    else:
        delta_pct = (delta_abs / start_point.value) * 100

    return {
        "kpi_id": kpi_id,
        "latest": {"ts": latest_point.ts, "value": latest_point.value},
        "start": {"ts": start_point.ts, "value": start_point.value},
        "delta_abs": delta_abs,
        "delta_pct": delta_pct,
    }
