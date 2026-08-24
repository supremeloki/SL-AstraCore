from astra.core.logger import get_logger
from astra.models.context_pack import ContextPack
from astra.models.dependency_snapshot import DependencySnapshot, RiskSummary
from astra.models.graph_node import NodeType
from astra.models.task_analysis import TaskAnalysis

logger = get_logger("astra.context.context_selector")


class ContextSelector:
    def __init__(self, graph_query, ranking):
        self._gq = graph_query
        self._ranking = ranking

    def select(self, task_analysis, strategy):
        seeds = self._collect_seeds(task_analysis)
        if not seeds:
            logger.warning("No seed nodes found for task")
            seeds = self._gq.find_entry_points()[:5]

        relevant = set(seeds)
        max_nodes = strategy.get("max_nodes", 30)

        for seed in seeds:
            upstream = self._gq.upstream(seed, strategy.get("depth_upstream", 2))
            for nid, _, _ in upstream:
                relevant.add(nid)
                if len(relevant) >= max_nodes:
                    break
            downstream = self._gq.downstream(seed, strategy.get("depth_downstream", 2))
            for nid, _, _ in downstream:
                relevant.add(nid)
                if len(relevant) >= max_nodes:
                    break

        if strategy.get("include_config"):
            relevant.update(self._collect_configs())

        relevant_list = list(relevant)
        ranked = self._ranking.rank(relevant_list, task_analysis)
        top = [nid for nid, _ in ranked[:max_nodes]]

        relevant_concepts = []
        for nid in top:
            relevant_concepts.extend(self._gq.related_vault_concepts(nid))

        conflicts = []
        if strategy.get("include_conflicts"):
            conflicts = self._gq.find_conflicts_for(top)

        patterns = self._gq.find_patterns_for(top)

        decisions = []
        for nid in top:
            if nid.startswith("decision:"):
                decisions.append(nid)

        required_files = self._extract_files(top)
        deps = self._build_dependency_snapshot(top)
        risks = self._build_risk_summary(top)
        hidden = self._detect_hidden_risks(top, conflicts)

        relevant_nodes = []
        for nid in top:
            node = self._gq.get_node(nid)
            if node:
                relevant_nodes.append({
                    "id": nid,
                    "label": node.label,
                    "type": node.node_type.value,
                    "confidence": node.confidence,
                    "layer": node.layer,
                    "risk": node.properties.get("risk", "low"),
                })

        pack = ContextPack(
            task=task_analysis.task,
            relevant_nodes=relevant_nodes,
            relevant_concepts=list(set(relevant_concepts))[:15],
            relevant_decisions=decisions,
            relevant_patterns=patterns,
            critical_dependencies=self._critical_edges(top),
            conflicts_to_watch=conflicts,
            required_files=required_files,
            hidden_risks=hidden,
            confidence=task_analysis.confidence,
            task_type=task_analysis.task_type.value,
        )
        return pack, deps, risks

    def _collect_seeds(self, task_analysis):
        seeds = set()
        for scope in task_analysis.target_scope:
            seeds.update(self._gq.find_by_path(scope))
        for kw in task_analysis.keywords:
            seeds.update(self._gq.find_by_keyword(kw))
        return list(seeds)

    def _collect_configs(self):
        configs = []
        for node in self._gq._kg.nodes:
            if node.node_type == NodeType.CONFIG:
                configs.append(node.id)
        return configs

    def _extract_files(self, node_ids):
        files = []
        for nid in node_ids:
            node = self._gq.get_node(nid)
            if node and node.node_type == NodeType.FILE:
                files.append(node.label)
            elif nid.startswith("file:"):
                node = self._gq.get_node(nid)
                if node:
                    files.append(node.label)
        return sorted(set(files))

    def _build_dependency_snapshot(self, node_ids):
        direct = []
        upstream = []
        downstream = []
        cycles = []

        adj = {e.from_node: e.to_node for e in self._gq._kg.edges}
        rev_adj = {e.to_node: e.from_node for e in self._gq._kg.edges}

        for nid in node_ids:
            up = self._gq.upstream(nid, 1)
            for target, etype, depth in up:
                if depth == 1:
                    direct.append({"from": target, "to": nid, "type": etype})
                    upstream.append(target)
            down = self._gq.downstream(nid, 1)
            for target, etype, depth in down:
                if depth == 1:
                    direct.append({"from": nid, "to": target, "type": etype})
                    downstream.append(target)

        return DependencySnapshot(
            direct=direct[:50],
            upstream=list(set(upstream))[:20],
            downstream=list(set(downstream))[:20],
            cycles=cycles,
        )

    def _build_risk_summary(self, node_ids):
        high = []
        medium = []
        volatile = []
        for nid in node_ids:
            node = self._gq.get_node(nid)
            if not node:
                continue
            risk = node.properties.get("risk", "low")
            if risk == "high":
                high.append(nid)
            elif risk == "medium":
                medium.append(nid)
            stability = node.properties.get("stability", "stable")
            if stability == "volatile":
                volatile.append(nid)
        total = max(len(node_ids), 1)
        risk_score = (len(high) * 3 + len(medium) * 1) / total
        return RiskSummary(
            high_risk_nodes=high,
            medium_risk_nodes=medium,
            volatile_nodes=volatile,
            overall_risk_score=round(min(risk_score, 5.0), 2),
        )

    def _detect_hidden_risks(self, node_ids, conflicts):
        risks = []
        node = None
        for nid in node_ids:
            n = self._gq.get_node(nid)
            if n and n.is_orphan:
                risks.append(f"orphan node: {n.label}")
            if n and n.properties.get("stability") == "volatile":
                risks.append(f"volatile node: {n.label}")
        if conflicts:
            risks.append(f"{len(conflicts)} related conflict(s) require attention")
        high_risk = [nid for nid in node_ids if self._gq.get_node(nid) and self._gq.get_node(nid).properties.get("risk") == "high"]
        if high_risk:
            risks.append(f"{len(high_risk)} high-risk node(s) in context")
        return risks

    def _critical_edges(self, node_ids):
        node_set = set(node_ids)
        critical = []
        for edge in self._gq._kg.edges:
            if edge.from_node in node_set and edge.to_node in node_set:
                critical.append({
                    "from": edge.from_node,
                    "to": edge.to_node,
                    "type": (edge.edge_type.value if hasattr(edge, "edge_type") else (edge.type.value if hasattr(edge.type, "value") else str(edge.type))),
                    "weight": getattr(edge, "weight", 1.0),
                })
            if len(critical) >= 50:
                break
        return critical
