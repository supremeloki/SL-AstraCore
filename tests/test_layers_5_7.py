import os
import tempfile
import unittest

from astra.blueprint import BlueprintEngine
from astra.execution import ExecutionEngine
from astra.models import (
    ArchitectureGraph,
    ChangeSpec,
    ChangeType,
    ContextPack,
    FileCategory,
    FileNode,
    FileSemantic,
    GraphEdge,
    GraphNode,
    ImplementationBlueprint,
    KnowledgeGraph,
    ProjectIndex,
    SemanticIndex,
)
from astra.models.graph_edge import EdgeType
from astra.models.graph_node import NodeType
from astra.runtime import RuntimeBrain


def sample_system():
    file_node = FileNode(
        path="astra/core/config.py",
        rel_path="astra/core/config.py",
        category=FileCategory.SOURCE,
        language="python",
        extension=".py",
        lines_count=12,
    )
    semantic = FileSemantic(
        path="astra/core/config.py",
        purpose="provide system configuration",
        role="logic",
        responsibilities=["define configuration"],
        outputs=["Config"],
        architecture_layer="infrastructure",
        risk_level="high",
        confidence=0.9,
    )
    project_index = ProjectIndex(files=[file_node])
    semantic_index = SemanticIndex(file_semantics=[semantic])
    node = GraphNode(
        id="file:astra/core/config.py",
        label="astra/core/config.py",
        node_type=NodeType.FILE,
        properties={"risk": "high", "dependencies": [], "outputs": ["Config"]},
        layer="infrastructure",
        confidence=0.9,
    )
    edge = GraphEdge(
        from_node="file:astra/core/config.py",
        to_node="symbol:Config",
        edge_type=EdgeType.REFERENCES,
        confidence=0.8,
    )
    graph = KnowledgeGraph(
        nodes=[node],
        edges=[edge],
        node_index={node.id: node},
        architecture=ArchitectureGraph(
            layers={"infrastructure": [node.id]},
            entry_points=[node.id],
        ),
        entry_points=[node.id],
    )
    return project_index, semantic_index, graph


class LayerEngineTests(unittest.TestCase):
    def test_runtime_brain_builds_dashboard(self):
        project_index, semantic_index, graph = sample_system()
        brain = RuntimeBrain(project_index, semantic_index, graph)

        dashboard = brain.dashboard()

        self.assertEqual(dashboard.project_health.files_total, 1)
        self.assertEqual(dashboard.project_health.graph_nodes, 1)
        self.assertEqual(dashboard.project_health.high_risk_count, 1)
        self.assertEqual(dashboard.knowledge_coverage["semantic_ratio"], 1.0)

    def test_blueprint_maps_existing_files_and_modules(self):
        project_index, semantic_index, graph = sample_system()
        context_pack = ContextPack(
            task="change config",
            required_files=["astra/core/config.py"],
            confidence=0.8,
        )

        blueprint = BlueprintEngine().build(
            "change config",
            project_index,
            semantic_index,
            graph,
            context_pack,
        )

        self.assertIsInstance(blueprint, ImplementationBlueprint)
        self.assertEqual(blueprint.files[0].path, "astra/core/config.py")
        self.assertEqual(blueprint.files[0].action, "modify")
        self.assertEqual(blueprint.modules[0].name, "astra/core")

    def test_execution_engine_validates_and_applies_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = ChangeSpec(
                file_path="generated.py",
                change_type=ChangeType.CREATE_FILE,
                after="VALUE = 1\n",
                reason="create test file",
                confidence=0.9,
            )
            engine = ExecutionEngine(root_path=tmp)

            result = engine.build_patch_set([spec])
            applied = engine.apply(result)

            self.assertTrue(applied.applied)
            self.assertEqual(applied.confidence, 1.0)
            self.assertTrue(os.path.exists(os.path.join(tmp, "generated.py")))
            self.assertEqual(applied.rollback_plan.steps[0]["action"], "delete created file")


if __name__ == "__main__":
    unittest.main()
