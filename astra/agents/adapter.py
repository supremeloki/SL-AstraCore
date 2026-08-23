from __future__ import annotations

from typing import Optional, Protocol, Sequence

from astra.ir.models import IREdge, IRNode, IRContextPack
from astra.agents.models import AgentRequest, AgentResponse, ExecutionStatus
from astra.agents.providers import BaseAgentProvider, GenericProvider


class AgentAdapter(Protocol):
    def build_request(
        self,
        task_description: str,
        context: IRContextPack,
        tools: Optional[Sequence[str]] = None,
    ) -> AgentRequest: ...

    def execute(
        self,
        task_description: str,
        context: IRContextPack,
        response_text: str = "",
    ) -> AgentResponse: ...


class AgentAdapterLayer:
    """Unified agent-execution interface.

    Translates context packs into agent requests.
    Translates agent responses into structured results.
    Provider-agnostic. No LLM-specific logic in Core.
    """

    def __init__(
        self,
        providers: Optional[Sequence[BaseAgentProvider]] = None,
    ) -> None:
        self._providers: list[BaseAgentProvider] = list(providers) if providers else [GenericProvider()]
        self._fallback = GenericProvider()

    def register(self, provider: BaseAgentProvider) -> None:
        self._providers.append(provider)

    def unregister(self, provider_name: str) -> None:
        self._providers = [p for p in self._providers if p.name != provider_name]

    def providers(self) -> tuple[BaseAgentProvider, ...]:
        return tuple(self._providers)

    def resolve_provider(self, task_description: str) -> BaseAgentProvider:
        # Simple resolution: prefer code-first providers for code tasks
        task_lower = task_description.lower()
        if any(kw in task_lower for kw in ("code", "implement", "refactor", "fix", "debug")):
            for p in self._providers:
                if p.name == "codex":
                    return p

        if any(kw in task_lower for kw in ("document", "docs", "explain", "summarize", "write documentation")):
            for p in self._providers:
                if p.name == "generic":
                    return p
        return self._providers[0] if self._providers else self._fallback

    def build_request(
        self,
        task_description: str,
        context: IRContextPack,
        tools: Optional[Sequence[str]] = None,
    ) -> AgentRequest:
        provider = self.resolve_provider(task_description)

        payload = {
            "nodes": [{"id": n.node_id, "name": n.name, "type": n.node_type.name} for n in context.nodes],
            "edges": [{"from": e.from_node, "to": e.to_node, "type": e.edge_type.name} for e in context.edges],
            "confidence": context.confidence,
            "token_budget": context.token_budget,
            "query_intent": context.query_intent,
        }

        return AgentRequest(
            task_description=task_description,
            context_payload=payload,
            tools_available=tuple(tools) if tools else (),
            constraints=(
                "operate_only_on_provided_context",
                "return_structured_output",
                "do_not_modify_graph_directly",
            ),
            expected_output_schema={"action": "str", "target": "str", "rationale": "str"},
        )

    def adapt_response(self, response: AgentResponse) -> AgentResponse:
        if response.execution_status is None:
            response.execution_status = (
                response.content and "completed" or "failed"
            )
        return response

    def execute(
        self,
        task_description: str,
        context: IRContextPack,
        response_text: str = "",
    ) -> AgentResponse:
        request = self.build_request(task_description, context)
        provider = self.resolve_provider(task_description)

        if response_text:
            return AgentResponse(
                content=response_text,
                execution_status=ExecutionStatus.COMPLETED,
                provider=provider.name,
                confidence=0.7,
            )

        return AgentResponse(
            content=task_description,
            execution_status=ExecutionStatus.PENDING,
            provider=provider.name,
            confidence=0.5,
        )
