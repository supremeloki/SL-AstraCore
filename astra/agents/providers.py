from __future__ import annotations

import shutil
import subprocess
from typing import Callable, Optional

from astra.agents.models import (
    AgentRequest,
    AgentResponse,
    ExecutionStatus,
    ProviderCapabilities,
    ToolCapability,
)
from astra.core.logger import get_logger

logger = get_logger("astra.agents.providers")


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
    """Codex CLI provider bridge — runs the real `codex` binary when present."""

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

    def __init__(self, binary: str = "codex", timeout_seconds: int = 300) -> None:
        self._binary = binary
        self._timeout = timeout_seconds

    @staticmethod
    def is_available() -> bool:
        return shutil.which("codex") is not None

    @staticmethod
    def _resolve_binary() -> str:
        """Windows: npm shims are .cmd files; subprocess needs the real extension."""
        import os
        cmd = shutil.which("codex")
        if cmd and os.name == "nt" and not cmd.lower().endswith((".cmd", ".exe", ".bat")):
            for candidate in (cmd + ".cmd", cmd + ".exe"):
                if os.path.isfile(candidate):
                    return candidate
        return cmd or "codex"

    def execute(self, request: AgentRequest) -> AgentResponse:
        if not self.is_available():
            return AgentResponse(
                content=f"codex CLI not found on PATH; task queued: {request.task_description}",
                errors=("codex-binary-missing",),
                execution_status=ExecutionStatus.FAILED,
                provider=self.name,
            )

        prompt_lines = [f"# Task\n{request.task_description}", ""]
        if request.context_payload.get("nodes"):
            prompt_lines.append("# Relevant context")
            for node in request.context_payload["nodes"][:50]:
                prompt_lines.append(f"- [{node.get('type')}] {node.get('id')} ({node.get('name')})")
        if request.tools_available:
            prompt_lines.append("")
            prompt_lines.append(f"# Allowed tools: {', '.join(request.tools_available)}")
        for constraint in request.constraints:
            prompt_lines.append(f"- constraint: {constraint}")
        prompt_text = "\n".join(prompt_lines)

        try:
            proc = subprocess.run(
                [self._resolve_binary(), "exec", "--json", "-"],
                input=prompt_text.encode("utf-8"),
                capture_output=True,
                timeout=self._timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return AgentResponse(
                content="codex exec timed out",
                errors=("timeout",),
                execution_status=ExecutionStatus.FAILED,
                provider=self.name,
            )
        except OSError as exc:
            return AgentResponse(
                content=f"failed to launch codex: {exc}",
                errors=("launch-failed",),
                execution_status=ExecutionStatus.FAILED,
                provider=self.name,
            )

        output = proc.stdout.decode("utf-8", errors="replace")
        status = ExecutionStatus.COMPLETED if proc.returncode == 0 else ExecutionStatus.FAILED
        return AgentResponse(
            content=output or proc.stderr.decode("utf-8", errors="replace"),
            structured_actions=({"provider": "codex", "exit_code": proc.returncode},),
            reasoning_trace=tuple(line for line in output.splitlines() if line.strip())[:20],
            errors=() if proc.returncode == 0 else (f"exit {proc.returncode}",),
            execution_status=status,
            provider=self.name,
        )


class ManualProvider(BaseAgentProvider):
    """Hands the task to a human: renders a hand-off brief and waits for pasted output.

    Useful when the user wants to run the task themselves in VS Code or any agent.
    """

    name = "manual"
    capabilities = ProviderCapabilities(
        tools=(ToolCapability.FILE_READ, ToolCapability.FILE_WRITE, ToolCapability.CONTEXT_RETRIEVAL),
        supports_streaming=False,
        supports_structured_output=False,
        model="human",
    )

    def __init__(self, response_callback: Optional[Callable[[AgentRequest], str]] = None) -> None:
        self._callback = response_callback

    def execute(self, request: AgentRequest) -> AgentResponse:
        brief_lines = [
            "## Task brief (for manual execution)",
            "",
            request.task_description,
            "",
            "### Context nodes",
        ]
        for node in request.context_payload.get("nodes", [])[:30]:
            brief_lines.append(f"- {node.get('id')} ({node.get('name')})")

        if self._callback is not None:
            result_text = self._callback(request)
            return AgentResponse(
                content=result_text,
                execution_status=ExecutionStatus.COMPLETED,
                provider=self.name,
                confidence=0.9,
            )

        return AgentResponse(
            content="\n".join(brief_lines),
            structured_actions=({"provider": "manual", "action": "await_external_result"},),
            execution_status=ExecutionStatus.PENDING,
            provider=self.name,
        )