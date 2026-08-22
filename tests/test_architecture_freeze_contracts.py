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


def test_protocol_contracts_exist():
    assert ParserEngine is not None
    assert KnowledgeGraph is not None
    assert GraphQueryEngine is not None
    assert ContextEngine is not None
