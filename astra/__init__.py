__all__ = [
    "AstraCore",
    "RuntimeBrain",
    "RuntimeOrchestrator",
    "BlueprintEngine",
    "ExecutionEngine",
    "UniversalParser",
    "DomainGraphEngine",
    "DashboardControlPlane",
    "AgentAdapterLayer",
]


def __getattr__(name):
    if name == "AstraCore":
        from astra.core.astra_core import AstraCore
        return AstraCore
    if name == "RuntimeBrain":
        from astra.runtime.runtime_brain import RuntimeBrain
        return RuntimeBrain
    if name == "RuntimeOrchestrator":
        from astra.runtime.orchestrator import RuntimeOrchestrator
        return RuntimeOrchestrator
    if name == "BlueprintEngine":
        from astra.blueprint.blueprint_engine import BlueprintEngine
        return BlueprintEngine
    if name == "ExecutionEngine":
        from astra.execution.execution_engine import ExecutionEngine
        return ExecutionEngine
    if name == "UniversalParser":
        from astra.parser.universal_parser import UniversalParser
        return UniversalParser
    if name == "DomainGraphEngine":
        from astra.graph.graph_engine import DomainGraphEngine
        return DomainGraphEngine
    if name == "DashboardControlPlane":
        from astra.dashboard.control_plane import DashboardControlPlane
        return DashboardControlPlane
    if name == "AgentAdapterLayer":
        from astra.agents import AgentAdapterLayer
        return AgentAdapterLayer
    raise AttributeError(name)
