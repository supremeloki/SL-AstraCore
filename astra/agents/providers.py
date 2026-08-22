from __future__ import annotations

from typing import Any, Optional

from astra.agents.models import (
    AgentRequest,
    AgentResponse,
    ExecutionStatus,
    ProviderCapabilities,
    ToolCapability,
)


class BaseAgentProvider:
    """Protocol for all agent/LLM providers."""

    name: str = "base"
    capabilities: ProviderCapabilities

    def execute(self, request: AgentRequest) -> AgentResponse:
        raise NotImplementedError

    def supports_tool(self, tool: ToolCapability) -> bool:
        return tool in self.capabilities.tools


class GenericProvider(BaseAgentProvider):
    """Fallback provider — wraps any text-generating endpoint."""

    name = "generic"
    capabilities = ProviderCapabilities(
        tools=(
            ToolCapability.FILE_READ,
            ToolCapability.CONTEXT_RETRIEVAL,
            ToolCapability.STRUCTURED_OUTPUT,
        ),
        supports_streaming=False,
        supports_structured_output=True,
        model="generic",
    )

    def execute(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(
            content=f"Task received: {request.task_description}",
            execution_status=ExecutionStatus.COMPLETED,
            provider=self.name,
        )


class CodexProvider(BaseAgentProvider):
    """Codex CLI provider bridge."""
    name = "codex"
    capabilities = ProviderCapabilities(
        tools=(
            ToolCapability.FILE_READ,
            ToolCapability.FILE_WRITE,
            ToolCapability.CODE_EXECUTION,
            ToolCapability.STRUCTURED_OUTPUT,
        ),
        supports_streaming=True,
        supports_structured_output=True,
        model="codex",
    )

    def execute(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(
            content=request.task_description,
            structured_actions=({"provider": "codex", "action": "execute"},),
            execution_status=ExecutionStatus.PENDING,
            provider=self.name,
        )