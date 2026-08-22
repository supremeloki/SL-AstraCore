from astra.models.agent import (
    AgentExecutionResult,
    AgentKind,
    AgentProfile,
    AgentRequest,
    NormalizedOutput,
)


class AgentAdapterLayer:
    def __init__(self, agents=None):
        self._agents = agents or [
            AgentProfile(name="codex", kind=AgentKind.CODEX, reliability=0.8, capabilities=["code", "analysis"]),
            AgentProfile(name="generic", kind=AgentKind.GENERIC, reliability=0.5, capabilities=["analysis"]),
        ]

    def select_agent(self, task_type="analysis"):
        candidates = sorted(self._agents, key=lambda a: (task_type not in a.capabilities, -a.reliability, a.cost_rank))
        return candidates[0]

    def adapt_context(self, context_pack, agent):
        payload = {
            "task": context_pack.task,
            "nodes": context_pack.relevant_nodes,
            "concepts": context_pack.relevant_concepts,
            "files": context_pack.required_files,
            "risks": context_pack.hidden_risks,
            "confidence": context_pack.confidence,
        }
        if agent.kind == AgentKind.CODEX:
            payload["format"] = "code-first"
        elif agent.kind == AgentKind.CLAUDE:
            payload["format"] = "structured-reasoning"
        elif agent.kind == AgentKind.HERMES:
            payload["format"] = "multi-step-reasoning"
        else:
            payload["format"] = "generic"
        return payload

    def build_request(self, task, context_pack, task_type="analysis"):
        agent = self.select_agent(task_type)
        return agent, AgentRequest(
            system_prompt="Use the provided context only. Do not bypass the orchestrator.",
            context_payload=self.adapt_context(context_pack, agent),
            task_description=task,
            constraints=[
                "do not modify graph directly",
                "do not bypass orchestrator",
                "return structured actions",
            ],
            tool_access=["filesystem_bridge", "graph_query_bridge", "context_bridge", "execution_bridge"],
            expected_output_schema={"actions": "list", "confidence": "float", "errors": "list"},
        )

    def normalize_response(self, response):
        text = response or ""
        return NormalizedOutput(
            raw_response=text,
            structured_actions=[],
            extracted_code_changes=[],
            reasoning_trace=[],
            confidence_score=0.5 if text else 0.0,
            detected_errors=[] if text else ["empty response"],
        )

    def execute(self, task, context_pack, response="", task_type="analysis"):
        agent, request = self.build_request(task, context_pack, task_type)
        normalized = self.normalize_response(response)
        return AgentExecutionResult(
            selected_agent=agent.name,
            request_payload=request,
            response=response,
            normalized_output=normalized,
            execution_status="normalized" if response else "request_built",
            fallback_chain_used=[],
        )
