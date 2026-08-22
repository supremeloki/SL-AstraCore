from collections import defaultdict

from astra.core.logger import get_logger
from astra.models.blueprint import (
    ArchitectureOverview,
    BuildStep,
    DependencyMap,
    FileBlueprint,
    ImplementationBlueprint,
    ModuleBlueprint,
    MvpSpec,
    RiskReport,
    TechnologyStack,
)

logger = get_logger("astra.blueprint.blueprint_engine")


class BlueprintEngine:
    def build(self, task, project_index, semantic_index, knowledge_graph, context_pack=None):
        logger.info("Blueprint started: implementation blueprint")
        modules = self._modules(semantic_index)
        files = self._files(semantic_index, context_pack)
        blueprint = ImplementationBlueprint(
            task=task,
            architecture=self._architecture(knowledge_graph, modules),
            modules=modules,
            files=files,
            technology_stack=self._technology_stack(project_index),
            build_order=self._build_order(modules),
            mvp=self._mvp(task),
            risks=self._risks(semantic_index, knowledge_graph, context_pack),
            dependency_map=self._dependency_map(semantic_index, knowledge_graph),
            execution_roadmap=self._roadmap(modules),
            confidence=self._confidence(project_index, semantic_index, knowledge_graph),
            metadata={"layer": 6, "source": "SL-AstraCore blueprint engine"},
        )
        logger.info("Blueprint complete: modules=%d files=%d", len(modules), len(files))
        return blueprint

    def _architecture(self, kg, modules):
        return ArchitectureOverview(
            style="modular-layered",
            boundaries=kg.architecture.boundaries,
            core_modules=[m.name for m in modules if m.name in ("astra/core", "astra/knowledge", "astra/context")],
            external_integrations=self._external_integrations(kg),
            decisions=[d.id for d in kg.decisions.decisions] if kg.decisions else [],
        )

    def _modules(self, semantic_index):
        grouped = defaultdict(list)
        for fs in semantic_index.file_semantics:
            parts = fs.path.replace("\\", "/").split("/")
            module = "/".join(parts[:2]) if len(parts) > 1 else parts[0]
            grouped[module].append(fs)

        modules = []
        for name, semantics in sorted(grouped.items()):
            dependencies = sorted({dep for fs in semantics for dep in fs.dependencies})
            outputs = sorted({out for fs in semantics for out in fs.outputs})
            inputs = sorted({inp for fs in semantics for inp in fs.inputs})
            modules.append(ModuleBlueprint(
                name=name,
                purpose=self._module_purpose(semantics),
                responsibilities=sorted({r for fs in semantics for r in fs.responsibilities}),
                internal_files=[fs.path for fs in semantics],
                dependencies=dependencies,
                inputs=inputs,
                outputs=outputs,
                api_contracts=self._api_contracts(semantics),
            ))
        return modules

    def _files(self, semantic_index, context_pack):
        required = set(context_pack.required_files) if context_pack else set()
        files = []
        for fs in semantic_index.file_semantics:
            action = "modify" if fs.path in required else "preserve"
            reason = "selected by context pack" if fs.path in required else "existing mapped component"
            files.append(FileBlueprint(
                path=fs.path,
                purpose=fs.purpose,
                role=fs.role,
                contains=fs.internal_entities,
                connects_to=fs.dependencies + fs.dependents,
                action=action,
                reason=reason,
            ))
        return files

    def _technology_stack(self, project_index):
        config_names = {f.rel_path.lower() for f in project_index.files}
        decisions = []
        backend = "python"
        frontend = ""
        database = ""
        graph_storage = "in-memory graph"
        cache_layer = ""
        queue_system = ""
        ai_integration = "context-pack interface"

        if "requirements.txt" in config_names:
            decisions.append("Python dependencies are declared through requirements.txt.")
        if any("fastapi" in getattr(f, "rel_path", "").lower() for f in project_index.files):
            frontend = "dashboard/api surface"
        if any("astra.yaml" == f.rel_path.lower() for f in project_index.files):
            decisions.append("astra.yaml is the project configuration source.")
        database = "duckdb/sqlite configured" if any("astra.yaml" == f.rel_path.lower() for f in project_index.files) else ""
        return TechnologyStack(
            backend=backend,
            frontend=frontend,
            database=database,
            graph_storage=graph_storage,
            cache_layer=cache_layer,
            queue_system=queue_system,
            ai_integration=ai_integration,
            decisions=decisions,
        )

    def _build_order(self, modules):
        preferred = [
            ("foundational core", ["astra/core", "astra/models"]),
            ("data acquisition", ["astra/scanner", "astra/reader", "astra/parser"]),
            ("semantic model", ["astra/knowledge"]),
            ("context engine", ["astra/context"]),
            ("runtime brain", ["astra/runtime"]),
            ("dashboard surface", ["astra/dashboard"]),
            ("blueprint engine", ["astra/blueprint"]),
            ("execution engine", ["astra/execution"]),
        ]
        existing = {m.name for m in modules}
        steps = []
        for idx, (name, module_names) in enumerate(preferred, 1):
            active = [m for m in module_names if m in existing or m in ("astra/runtime", "astra/blueprint", "astra/execution")]
            if not active:
                continue
            steps.append(BuildStep(
                order=idx,
                name=name,
                modules=active,
                validation=[f"import {m.replace('/', '.')}" for m in active if m.startswith("astra/")],
                rollback=["revert files changed in this step"],
            ))
        return steps

    def _mvp(self, task):
        return MvpSpec(
            must_work=[
                "Build project index from files",
                "Build semantic model",
                "Build knowledge graph",
                "Build task-scoped context pack",
                "Expose runtime dashboard and ask-project outputs",
                "Generate implementation blueprint",
                "Generate validated execution patch set",
            ],
            excluded=[
                "Autonomous large-scale refactors without explicit patch specs",
                "Remote AI provider calls",
                "Persistent multi-user dashboard state",
            ],
            acceptance_checks=[
                "Layer engines can be imported",
                "Phase 4 returns a context pack",
                "Phase 5 returns runtime/dashboard data",
                "Blueprint maps files and modules",
                "Execution returns patches with rollback steps",
            ],
        )

    def _risks(self, semantic_index, kg, context_pack):
        high = [fs.path for fs in semantic_index.file_semantics if fs.risk_level == "high"]
        medium = [fs.path for fs in semantic_index.file_semantics if fs.risk_level == "medium"]
        context_risks = context_pack.hidden_risks if context_pack else []
        return RiskReport(
            technical=high[:10],
            scaling=["large repositories may require persistent graph storage"] if len(kg.nodes) > 10000 else [],
            complexity=medium[:10],
            dependency=[c.description for c in semantic_index.conflicts[:10]],
            ai_context=context_risks,
        )

    def _dependency_map(self, semantic_index, kg):
        module_deps = defaultdict(set)
        for fs in semantic_index.file_semantics:
            module = "/".join(fs.path.replace("\\", "/").split("/")[:2])
            for dep in fs.dependencies:
                module_deps[module].add(dep)
        return DependencyMap(
            module_dependencies={k: sorted(v) for k, v in module_deps.items()},
            critical_paths=[{"from": e.from_node, "to": e.to_node, "type": e.edge_type.value} for e in kg.edges[:25]],
            bottlenecks=[n.id for n in kg.nodes if len(n.properties.get("dependencies", [])) > 10],
            circular_risks=[c.description for c in semantic_index.conflicts if c.conflict_type.value == "architecture"],
        )

    def _roadmap(self, modules):
        return [
            {"order": step.order, "name": step.name, "modules": step.modules}
            for step in self._build_order(modules)
        ]

    def _module_purpose(self, semantics):
        purposes = [fs.purpose for fs in semantics if fs.purpose and fs.purpose != "unknown"]
        return purposes[0] if purposes else "project module"

    def _api_contracts(self, semantics):
        contracts = []
        for fs in semantics:
            outputs = [out for out in fs.outputs if isinstance(out, str)]
            if outputs:
                contracts.append({"file": fs.path, "exports": outputs[:10]})
        return contracts

    def _external_integrations(self, kg):
        integrations = set()
        for node in kg.nodes:
            for dep in node.properties.get("dependencies", []):
                if isinstance(dep, str) and not dep.startswith("astra"):
                    integrations.add(dep.split(".")[0])
        return sorted(integrations)[:20]

    def _confidence(self, project_index, semantic_index, kg):
        score = 0.3
        if project_index.files:
            score += 0.2
        if semantic_index.file_semantics:
            score += 0.2
        if kg.nodes:
            score += 0.2
        if kg.edges:
            score += 0.1
        return round(min(score, 1.0), 2)
