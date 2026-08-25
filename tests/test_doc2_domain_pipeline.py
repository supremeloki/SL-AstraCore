import os
import tempfile
import unittest

from astra import AstraCore
from astra.graph import DomainGraphEngine
from astra.parser import UniversalParser
from astra.agents import AgentAdapterLayer
from astra.scanner import RepositoryScanner


class Doc2DomainPipelineTests(unittest.TestCase):
    def test_phase_1_to_7_domain_pipeline(self):
        with tempfile.TemporaryDirectory() as root:
            self._write(root, "astra/core/app.py", "import json\n\ndef run():\n    return json.dumps({'ok': True})\n")
            self._write(root, "docs/Idea.md", "# Idea\n\n[[astra/core/app.py]]\n")
            self._write(root, "astra.yaml", "project:\n  name: demo\n")

            system = AstraCore(root).build_system("review app architecture")

            self.assertGreaterEqual(system["phase1_repository_index"].metadata.files_indexed, 3)
            self.assertGreaterEqual(len(system["phase2_parse_index"].files), 3)
            self.assertGreater(len(system["phase3_knowledge_graph"].nodes), 0)
            self.assertIsNotNone(system["phase4_context"])
            self.assertIsNotNone(system["phase5_runtime_orchestrator"])
            self.assertTrue(system["phase6_dashboard"].events)
            self.assertIsNotNone(system["phase7_agent_adapter"])
            self.assertEqual(system["phase7_agent_adapter"].execution_status.value, "completed")

    def test_parser_and_graph_consume_repository_index_only(self):
        with tempfile.TemporaryDirectory() as root:
            self._write(root, "main.py", "def main():\n    print('hi')\n")

            repository_index = RepositoryScanner(root).scan_repository()
            parse_index = UniversalParser().parse_repository(repository_index)
            graph = DomainGraphEngine().build(repository_index, parse_index)

            self.assertEqual(parse_index.metadata["input_files"], 1)
            self.assertTrue(any(n.label == "main" for n in graph.nodes))
            self.assertGreaterEqual(len(graph.edges), 1)

    def test_agent_adapter_preserves_context_payload_shape(self):
        with tempfile.TemporaryDirectory() as root:
            self._write(root, "main.py", "def main():\n    return 1\n")
            system = AstraCore(root).build_system("analyze main")
            # Use the already-executed adapter result from the pipeline
            agent_result = system["phase7_agent_adapter"]

            self.assertEqual(agent_result.execution_status.value, "completed")
            self.assertIn("analyze main", agent_result.content)

    def _write(self, root, rel_path, content):
        path = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
