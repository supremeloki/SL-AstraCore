from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ToolCapability(str, Enum):
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    GRAPH_QUERY = "graph_query"
    CONTEXT_RETRIEVAL = "context_retrieval"
    CODE_EXECUTION = "code_execution"
    WEB_SEARCH = "web_search"
    STRUCTURED_OUTPUT = "structured_output"
    STREAMING = "streaming"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class AgentRequest:
    task_description: str
    context_payload: dict[str, Any]
    tools_available: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    expected_output_schema: Optional[dict[str, Any]] = None
    max_tokens: Optional[int] = None
    temperature: float = 0.1


@dataclass
class AgentResponse:
    content: str
    structured_actions: tuple[dict[str, Any], ...] = ()
    reasoning_trace: tuple[str, ...] = ()
    confidence: float = 0.5
    errors: tuple[str, ...] = ()
    execution_status: ExecutionStatus = ExecutionStatus.COMPLETED
    provider: str = "unknown"


@dataclass
class ProviderCapabilities:
    tools: tuple[ToolCapability, ...]
    supports_streaming: bool = False
    supports_structured_output: bool = False
    max_context_length: Optional[int] = None
    model: str = "unknown"