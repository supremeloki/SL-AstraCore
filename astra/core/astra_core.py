from astra.blueprint.blueprint_engine import BlueprintEngine
from astra.context.context_engine import ContextEngine
from astra.core.config import Config
from astra.core.logger import get_logger
from astra.dashboard.control_plane import DashboardControlPlane
from astra.execution.execution_engine import ExecutionEngine
from astra.graph.graph_engine import DomainGraphEngine
from astra.parser.universal_parser import UniversalParser
from astra.agents import AgentAdapterLayer
from astra.agents.bridge import legacy_pack_to_ir
from astra.runtime.orchestrator import RuntimeOrchestrator
from astra.scanner.repository_scanner import RepositoryScanner
from astra.legacy.adapters import to_legacy_project_index

logger = get_logger("astra.core.astra_core")


class AstraCore:
    def __init__(self, root_path=None, config=None):
        self.config = config or Config(root_path)
        self.root_path = self.config.project_path

    def build_system(self, task=""):
        logger.info("SL-AstraCore domain pipeline started")
        repository_index = RepositoryScanner(self.root_path, self.config).scan_repository()
        parse_index = UniversalParser().parse_repository(repository_index)
        knowledge_graph = DomainGraphEngine().build(repository_index, parse_index)

        context_output = None
        context_pack = None
        if task:
            context_output = ContextEngine(knowledge_graph).build_pack(task)
            context_pack = context_output[1]

        runtime = RuntimeOrchestrator(knowledge_graph)
        runtime_analysis = None
        if context_output:
            runtime_analysis = {
                "task_analysis": context_output[0],
                "context_pack": context_output[1],
                "dependency_snapshot": context_output[2],
                "risk_summary": context_output[3],
            }
        run_result = None
        dashboard = DashboardControlPlane().build(
            repository_index=repository_index,
            knowledge_graph=knowledge_graph,
            context_pack=context_pack,
            execution_state={"plan": []},
        )

        result = {
            "phase1_repository_index": repository_index,
            "phase2_parse_index": parse_index,
            "phase3_knowledge_graph": knowledge_graph,
            "phase4_context": context_output,
            "phase5_runtime_orchestrator": runtime,
            "phase5_execution_plan": None,
            "phase6_dashboard": dashboard,
        }

        if context_pack:
            ir_pack = legacy_pack_to_ir(context_pack)
            agent_result = AgentAdapterLayer(config=self.config).execute(task, ir_pack)
            result["phase7_agent_adapter"] = agent_result

        logger.info("SL-AstraCore domain pipeline ready")
        return result

    def build_implementation_blueprint(self, task):
        system = self.build_system(task)
        context_pack = system["phase4_context"][1] if system["phase4_context"] else None
        blueprint = BlueprintEngine().build(
            task,
            to_legacy_project_index(system["phase1_repository_index"]),
            self._legacy_semantic_index(system["phase2_parse_index"]),
            system["phase3_knowledge_graph"],
            context_pack,
        )
        system["implementation_blueprint"] = blueprint
        return system

    def prepare_execution(self, task, change_specs=None):
        system = self.build_implementation_blueprint(task)
        context_pack = system["phase4_context"][1] if system["phase4_context"] else None
        execution_result = ExecutionEngine(self.root_path).build_patch_set(
            change_specs or [],
            system["implementation_blueprint"],
            context_pack,
            system["phase3_knowledge_graph"],
        )
        system["execution_result"] = execution_result
        return system

    def build_project_brain(self, task=""):
        return self.build_system(task)

    def _legacy_project_index(self, repository_index):
        from astra.models.project_index import ProjectIndex

        index = ProjectIndex(files=repository_index.to_file_nodes())
        index.metadata = {
            "repository_index": repository_index,
            "repository_scan": repository_index.metadata,
            "language_summary": repository_index.language_summary,
            "failure_report": repository_index.failures,
        }
        return index

    def _legacy_semantic_index(self, parse_index):
        from astra.models.file_semantic import FileSemantic
        from astra.models.semantic_index import SemanticIndex

        semantics = []
        for parsed_file in parse_index.files:
            semantics.append(FileSemantic(
                path=parsed_file.file_path,
                purpose=f"parsed {parsed_file.language or 'unknown'} file",
                role="parsed_source",
                responsibilities=[e.kind.value for e in parsed_file.elements[:10]],
                dependencies=[d.target for d in parsed_file.dependencies],
                outputs=[e.name for e in parsed_file.elements[:20]],
                confidence=parsed_file.confidence,
            ))
        return SemanticIndex(
            file_semantics=semantics,
            metadata={
                "parse_index": parse_index,
                "parser_failures": parse_index.failures,
            },
        )
