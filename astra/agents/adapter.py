from __future__ import annotations

from typing import Optional, Protocol, Sequence

from astra.ir.models import IRContextPack
from astra.agents.models import AgentRequest, AgentResponse, ExecutionStatus
from astra.agents.providers import BaseAgentProvider, GenericProvider
from astra.core.logger import get_logger

logger = get_logger("astra.agents.adapter")


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


_PROVIDER_NAMES = ("generic", "codex", "manual")


def build_providers_from_config(config=None) -> list[BaseAgentProvider]:
    """Build the provider list from config `agent.providers` (default: generic).

    Providers are only registered if actually usable (e.g. codex requires the
    CLI binary on PATH).
    """
    from astra.agents.providers import CodexProvider, ManualProvider

    enabled = ["generic"]
    if config is not None:
        try:
            configured = config.get("agent.providers")
            if isinstance(configured, (list, tuple)) and configured:
                enabled = [str(p).strip().lower() for p in configured]
        except Exception:
            pass

    providers: list[BaseAgentProvider] = []
    for name in enabled:
        if name == "generic":
            providers.append(GenericProvider())
        elif name == "codex" and CodexProvider.is_available():
            providers.append(CodexProvider())
        elif name == "manual":
            providers.append(ManualProvider())
    return providers or [GenericProvider()]


class AgentAdapterLayer:
    """Unified agent-execution interface.

    Provider-agnostic. No LLM-specific logic in Core.
    """

    def __init__(
        self,
        providers: Optional[Sequence[BaseAgentProvider]] = None,
        config=None,
    ) -> None:
        if providers:
            self._providers: list[BaseAgentProvider] = list(providers)
        else:
            self._providers = build_providers_from_config(config)
        self._fallback = GenericProvider()

    def register(self, provider: BaseAgentProvider) -> None:
        self._providers.append(provider)

    def unregister(self, provider_name: str) -> None:
        self._providers = [p for p in self._providers if p.name != provider_name]

    def providers(self) -> tuple[BaseAgentProvider, ...]:
        return tuple(self._providers)

    def resolve_provider(self, task_description: str) -> BaseAgentProvider:
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
                ExecutionStatus.COMPLETED if response.content else ExecutionStatus.FAILED
            )
        return response

    def execute(
        self,
        task_description: str,
        context: IRContextPack,
        response_text: str = "",
        max_retries: int = 3,
        **kwargs,
    ) -> AgentResponse:
        """Execute with automatic retry and event emission."""
        attempt = 0
        while attempt < max_retries:
            try:
                # Event stream: attempt_started
                return self._do_execute(task_description, context, response_text)
            except Exception as exc:
                attempt += 1
                logger.warning("Execution attempt %d failed: %s", attempt, exc)
        raise RuntimeError(f"Execution failed after {max_retries} attempts")

    def _do_execute(self, task_description, context, response_text) -> AgentResponse:
        request = self.build_request(task_description, context)
        provider = self.resolve_provider(task_description)

        if response_text:
            return AgentResponse(
                content=response_text,
                execution_status=ExecutionStatus.COMPLETED,
                provider=provider.name,
                confidence=0.7,
            )

        return provider.execute(request)