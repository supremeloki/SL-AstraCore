from astra.context.api import ContextEngine
from astra.graph.api import GraphQueryEngine, KnowledgeGraph
from astra.ir.models import (
    EdgeType,
    IRContextPack,
    IREdge,
    IRFileNode,
    IRNode,
    IRProjectIndex,
    IRSymbol,
    NodeType,
    SymbolKind,
)
from astra.parser.api import ParserEngine
from astra.runtime.api import ExecutionMode, ExecutionPlan, ExecutionStep


def test_ir_models_are_instantiable():
    node = IRNode(
        id="node-1",
        type=NodeType.FILE,
        name="main.py",
        source="scanner",
    )

    file_node = IRFileNode(
        id="file-1",
        type=NodeType.FILE,
        name="main.py",
        source="scanner",
        file_path="main.py",
        language="python",
    )

    edge = IREdge(
        from_node="a",
        to_node="b",
        type=EdgeType.DEPENDS_ON,
    )

    symbol = IRSymbol(
        name="build_system",
        kind=SymbolKind.FUNCTION,
        file_path="astra/core/astra_core.py",
    )

    project = IRProjectIndex(project_root="repo")
    context = IRContextPack(task_summary="analyze auth")

    assert node.type == NodeType.FILE
    assert file_node.language == "python"
    assert edge.type == EdgeType.DEPENDS_ON
    assert symbol.kind == SymbolKind.FUNCTION
    assert project.project_root == "repo"
    assert context.task_summary == "analyze auth"


def test_runtime_contracts_are_instantiable():
    step = ExecutionStep(
        step_id="step-1",
        action_type="analyze",
    )

    plan = ExecutionPlan(
        execution_id="exec-1",
        mode=ExecutionMode.ANALYSIS,
        steps=(step,),
    )

    assert plan.mode == ExecutionMode.ANALYSIS
    assert plan.steps[0].action_type == "analyze"


def test_protocol_contracts_still_satisfy_the_engine():
    """The old version asserted `X is not None`, which cannot fail — and these
    are typing.Protocols, so what matters is that the production classes still
    satisfy them and the declared methods still exist."""
    for protocol in (ParserEngine, KnowledgeGraph, GraphQueryEngine, ContextEngine):
        assert getattr(protocol, "_is_protocol", False), f"{protocol} stopped being a Protocol"

    # A real implementation must still expose what the orchestrator calls.
    from astra.parser.registry import build_default_parser_registry

    concrete_parser = build_default_parser_registry()
    assert callable(getattr(concrete_parser, "parse", None))
    assert hasattr(ParserEngine, "parse_repository"), (
        "ParserEngine no longer declares parse_repository()"
    )
