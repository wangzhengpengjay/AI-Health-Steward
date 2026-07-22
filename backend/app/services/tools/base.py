"""Base class for health consultation tools.

Every tool that the AI consultation service can invoke inherits from HealthTool.
Tools receive a database session at execution time so they can query/write
the member's health profile without owning their own session lifecycle.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.base import ToolDefinition


class HealthTool(ABC):
    """Abstract base for all health-domain tools."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for function calling

    @abstractmethod
    async def execute(self, db: AsyncSession, member_id: int, **kwargs: Any) -> dict[str, Any]:
        """Execute the tool and return a JSON-serialisable result dict.

        Args:
            db: Async SQLAlchemy session (owned by the caller / request).
            member_id: The family member this tool operates on.
            **kwargs: Tool-specific parameters parsed from the model's arguments.
        """
        ...

    def to_tool_definition(self) -> ToolDefinition:
        """Convert to ToolDefinition for the model provider."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )
