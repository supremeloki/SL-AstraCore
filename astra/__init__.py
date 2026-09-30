"""SL-AstraCore — a code-intelligence tool for a single local repository.

The public surface is deliberately small. Everything below is either an entry
point (the dashboard, the CLI) or the orchestrator they share; the engines
that were only reachable through AstraCore are gone.
"""

__all__ = ["RuntimeOrchestrator"]


def __getattr__(name):
    if name == "RuntimeOrchestrator":
        from astra.runtime.orchestrator import RuntimeOrchestrator

        return RuntimeOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
