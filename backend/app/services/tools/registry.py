"""Tool registry — registers all health tools and provides lookup."""
from __future__ import annotations

from app.providers.base import ToolDefinition
from app.services.tools.base import HealthTool
from app.services.tools.extract_and_save import ExtractAndSaveTool
from app.services.tools.query_abnormal import QueryAbnormalTool
from app.services.tools.query_metrics import QueryMetricsTool
from app.services.tools.query_profile import QueryProfileTool


class ToolRegistry:
    """Registry of all available health consultation tools."""

    def __init__(self) -> None:
        self._tools: dict[str, HealthTool] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the built-in tool set."""
        self.register(QueryMetricsTool())
        self.register(QueryProfileTool())
        self.register(QueryAbnormalTool())
        self.register(ExtractAndSaveTool())

    def register(self, tool: HealthTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> HealthTool | None:
        """Look up a tool by name."""
        return self._tools.get(name)

    def get_all_tool_definitions(self) -> list[ToolDefinition]:
        """Return ToolDefinition list for all registered tools."""
        return [tool.to_tool_definition() for tool in self._tools.values()]

    def list_tool_names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())
