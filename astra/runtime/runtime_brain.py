from astra.context.context_engine import ContextEngine
from astra.context.graph_query import GraphQuery
from astra.core.logger import get_logger
from astra.models.runtime import (
    BrainAnswer,
    DashboardView,
    DebugTraceReport,
    ExecutionPlan,
    ProjectHealth,
    RuntimeMode,
    RuntimeResponse,
)

logger = get_logger("astra.runtime.runtime_brain")


class RuntimeBrain:
    def __init__(self, project_index, semantic_index, knowledge_graph):
        self._project_index = project_index
        self._semantic_index = semantic_index
        self._kg = knowledge_graph
        self._context_engine = ContextEngine(knowledge_graph)
        self._query = GraphQuery(knowledge_graph)

    def handle(self, mode, text=""):
        runtime_mode = RuntimeMode(mode)
        if runtime_mode == RuntimeMode.DASHBOARD:
            return RuntimeResponse(mode=runtime_mode, dashboard=self.dashboard())
        if runtime_mode == RuntimeMode.ASK_PROJECT:
            answer = self.ask(text)
            return RuntimeResponse(mode=runtime_mode, answer=answer)
        if runtime_mode == RuntimeMode.TASK_EXECUTION:
            plan, pack = self.plan_task(text)
            return RuntimeResponse(mode=runtime_mode, execution_plan=plan, context_pack=pack)
        if runtime_mode == RuntimeMode.DEBUG_TRACE:
            report, pack = self.debug_trace(text)
            return RuntimeResponse(mode=runtime_mode, debug_trace=report, context_pack=pack)
        raise ValueError(f"unsupported runtime mode: {mode}")

    def dashboard(self):
        health = self._project_health()
        return DashboardView(
            project_health=health,
            architecture_state=self._architecture_state(),
            dependency_state=self._dependency_state(),
            risk_hotspots=self._risk_hotspots(),
            conflict_overview=self._conflict_overview(),
            knowledge_coverage=self._knowledge_coverage(),
            entry_points=list(self._kg.entry_points),
            metadata={"mode": RuntimeMode.DASHBOARD.value},
        )

    def ask(self, question):
        task_analysis, pack, _, _ = self._context_engine.build_pack(question)
        node_labels = [n["label"] for n in pack.relevant_nodes]
        if not node_labels:
            return BrainAnswer(
                question=question,
                answer="No relevant project nodes were found for this question.",
                confidence=0.2,
                unknowns=["No graph seed matched the question."],
            )

        answer = self._compose_answer(question, pack, task_analysis)
        return BrainAnswer(
            question=question,
            answer=answer,
            used_nodes=[n["id"] for n in pack.relevant_nodes],
            used_decisions=pack.relevant_decisions,
            conflicts_considered=pack.conflicts_to_watch,
            required_files=pack.required_files,
            confidence=pack.confidence,
            unknowns=pack.hidden_risks,
        )

    def plan_task(self, task):
        task_analysis, pack, _, risks = self._context_engine.build_pack(task)
        steps = [
            {"order": 1, "action": "Review required files", "targets": pack.required_files},
            {"order": 2, "action": "Validate dependency impact", "targets": pack.critical_dependencies},
            {"order": 3, "action": "Apply minimal task-scoped change", "targets": [n["id"] for n in pack.relevant_nodes[:5]]},
            {"order": 4, "action": "Run focused validation", "targets": pack.required_files},
        ]
        plan = ExecutionPlan(
            task=task,
            steps=steps,
            affected_nodes=[n["id"] for n in pack.relevant_nodes],
            required_files=pack.required_files,
            risks=pack.hidden_risks + risks.high_risk_nodes + risks.medium_risk_nodes,
            confidence=task_analysis.confidence,
        )
        return plan, pack

    def debug_trace(self, task):
        _, pack, deps, _ = self._context_engine.build_pack(task)
        propagation = []
        for edge in pack.critical_dependencies:
            propagation.append({"from": edge.get("from"), "to": edge.get("to"), "type": edge.get("type")})
        report = DebugTraceReport(
            task=task,
            root_candidates=[n["id"] for n in pack.relevant_nodes[:5]],
            propagation_path=propagation or deps.direct,
            impacted_modules=list(set(deps.upstream + deps.downstream)),
            conflict_nodes=pack.conflicts_to_watch,
            confidence=pack.confidence,
        )
        return report, pack

    def _project_health(self):
        files_total = len(self._project_index.files)
        graph_nodes = len(self._kg.nodes)
        graph_edges = len(self._kg.edges)
        high_risk = [
            n for n in self._kg.nodes
            if n.properties.get("risk") == "high"
        ]
        conflicts = len(self._kg.conflicts.conflicts)
        orphans = len(self._kg.orphans.orphan_nodes)
        if conflicts or high_risk or orphans:
            stability = "attention_required"
        elif graph_nodes:
            stability = "stable"
        else:
            stability = "unknown"
        confidence = 0.4
        if files_total:
            confidence += 0.2
        if graph_nodes:
            confidence += 0.2
        if self._semantic_index.file_semantics:
            confidence += 0.2
        return ProjectHealth(
            stability=stability,
            files_total=files_total,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            high_risk_count=len(high_risk),
            conflict_count=conflicts,
            orphan_count=orphans,
            confidence=round(min(confidence, 1.0), 2),
        )

    def _architecture_state(self):
        arch = self._kg.architecture
        return {
            "layers": {k: len(v) for k, v in arch.layers.items()},
            "modules": arch.modules,
            "boundaries": arch.boundaries,
            "data_flow": arch.data_flow,
        }

    def _dependency_state(self):
        by_type = {}
        for edge in self._kg.edges:
            by_type[edge.edge_type.value] = by_type.get(edge.edge_type.value, 0) + 1
        return {"edge_types": by_type, "total_edges": len(self._kg.edges)}

    def _risk_hotspots(self):
        hotspots = []
        for node in self._kg.nodes:
            risk = node.properties.get("risk", "low")
            if risk in ("high", "medium") or node.is_orphan:
                hotspots.append({
                    "node": node.id,
                    "label": node.label,
                    "risk": risk,
                    "orphan": node.is_orphan,
                    "confidence": node.confidence,
                })
        return hotspots[:25]

    def _conflict_overview(self):
        return [
            {
                "id": c.id if hasattr(c, "id") else f"{c.source_a}->{c.source_b}",
                "source_a": c.source_a,
                "source_b": c.source_b,
                "type": c.conflict_type.value,
                "severity": c.severity.value,
                "description": c.description,
                "confidence": c.confidence,
            }
            for c in self._kg.conflicts.conflicts
        ]

    def _knowledge_coverage(self):
        files = len(self._project_index.files)
        semantics = len(self._semantic_index.file_semantics)
        vault_nodes = len(self._project_index.vault_nodes)
        concepts = len(self._semantic_index.vault_concepts)
        return {
            "files_with_semantics": semantics,
            "total_files": files,
            "semantic_ratio": round(semantics / files, 2) if files else 0.0,
            "vault_nodes": vault_nodes,
            "vault_concepts": concepts,
        }

    def _compose_answer(self, question, pack, task_analysis):
        top_nodes = ", ".join(n["label"] for n in pack.relevant_nodes[:5])
        parts = [
            f"Task type: {task_analysis.task_type.value}.",
            f"Most relevant project areas: {top_nodes}.",
        ]
        if pack.required_files:
            parts.append(f"Required files: {', '.join(pack.required_files[:8])}.")
        if pack.conflicts_to_watch:
            parts.append(f"Conflicts to watch: {len(pack.conflicts_to_watch)}.")
        if pack.hidden_risks:
            parts.append(f"Hidden risks: {', '.join(pack.hidden_risks[:5])}.")
        return " ".join(parts)
