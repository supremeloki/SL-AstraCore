from dataclasses import dataclass, field
from enum import Enum


class AgentKind(Enum):
    CODEX = "codex"
    HERMES = "hermes"
    GPT = "gpt"
    LOCAL_LLM = "local_llm"
    GENERIC = "generic"


@dataclass
class AgentProfile:
    name: str = ""
    kind: AgentKind = AgentKind.GENERIC
    context_limit: int = 32000
    reliability: float = 0.5
    cost_rank: int = 5
    capabilities: list = field(default_factory=list)


@dataclass
class AgentRequest:
    system_prompt: str = ""
    context_payload: object | None = None
    task_description: str = ""
    constraints: list = field(default_factory=list)
    tool_access: list = field(default_factory=list)
    expected_output_schema: dict = field(default_factory=dict)


@dataclass
class NormalizedOutput:
    raw_response: str = ""
    structured_actions: list = field(default_factory=list)
    extracted_code_changes: list = field(default_factory=list)
    reasoning_trace: list = field(default_factory=list)
    confidence_score: float = 0.0
    detected_errors: list = field(default_factory=list)


@dataclass
class AgentExecutionResult:
    selected_agent: str = ""
    request_payload: AgentRequest = field(default_factory=AgentRequest)
    response: str = ""
    normalized_output: NormalizedOutput = field(default_factory=NormalizedOutput)
    execution_status: str = "pending"
    fallback_chain_used: list = field(default_factory=list)
