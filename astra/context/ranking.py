from astra.core.logger import get_logger
from astra.models.graph_node import NodeType
from astra.models.task_analysis import TaskType

logger = get_logger("astra.context.ranking")

# Node types that describe the repo rather than its code.
_ANALYTIC_TYPES = (NodeType.PATTERN, NodeType.CONFLICT, NodeType.DECISION)


class Ranking:
    def __init__(self, knowledge_graph):
        self._kg = knowledge_graph
        self._adj = {}
        self._reverse_adj = {}
        self._build()

    def _build(self):
        from collections import defaultdict
        self._adj = defaultdict(int)
        self._reverse_adj = defaultdict(int)
        for edge in self._kg.edges:
            self._adj[edge.from_node] += 1
            self._reverse_adj[edge.to_node] += 1

    def score(self, node_id, task_analysis=None, terms=None):
        node = self._kg.node_index.get(node_id)
        if node is None:
            return 0.0
        score = 0.0
        node_type = node.node_type
        # Analytic labels — patterns, conflicts, decisions — are not source. A
        # context pack is a bundle of code for an agent to read, and these are
        # referenced by nearly every file, so degree alone floated
        # "naming:snake_case" to the top of every pack. Scaling the structural
        # part (rather than the total) keeps the demotion from being undone by
        # a high degree.
        structural_scale = 0.15 if node_type in _ANALYTIC_TYPES else 1.0

        if terms:
            # Dominant on purpose. A node's structural score tops out around 20
            # (degree, confidence, complexity) while a partial text match is
            # worth 15, so a file that actually mentions the query outranks a
            # merely central one instead of tying with it.
            score += 15.0 * self._text_match(node, terms)

        structural = 0.0
        structural += node.confidence * 1.5
        structural += self._adj.get(node_id, 0) * 0.3
        structural += self._reverse_adj.get(node_id, 0) * 0.4
        if node.is_orphan:
            structural *= 0.3
        risk = node.properties.get("risk", "low")
        if risk == "high":
            structural += 2.0
        elif risk == "medium":
            structural += 1.0
        if task_analysis:
            type_weights = self._type_weights(task_analysis.task_type)
            structural *= type_weights.get(node_type, 1.0)
        structural += min(node.properties.get("complexity", 0) / 50.0, 1.0)
        score += structural_scale * structural

        if node_type == NodeType.FILE:
            score += 0.5
        elif node_type == NodeType.CLASS:
            score += 0.7
        elif node_type == NodeType.FUNCTION:
            score += 0.6
        elif node_type == NodeType.VAULT_CONCEPT:
            score += 0.4
        if node_type in _ANALYTIC_TYPES:
            # The type bonus is what source gets for being source; an analytic
            # label gets none of it.
            score *= 0.2
        return round(score, 3)

    def _type_weights(self, task_type):
        return {
            TaskType.BUG_FIX: {
                NodeType.FILE: 1.5,
                NodeType.FUNCTION: 2.0,
                NodeType.CLASS: 1.2,
                NodeType.VAULT_CONCEPT: 0.8,
                NodeType.DECISION: 0.5,
                NodeType.PATTERN: 0.6,
                NodeType.CONFIG: 1.3,
            },
            TaskType.FEATURE_ADDITION: {
                NodeType.FILE: 1.5,
                NodeType.CLASS: 1.8,
                NodeType.FUNCTION: 1.2,
                NodeType.PATTERN: 1.4,
                NodeType.VAULT_CONCEPT: 1.0,
                NodeType.DECISION: 0.9,
                NodeType.CONFIG: 1.0,
            },
            TaskType.REFACTOR: {
                NodeType.FILE: 1.5,
                NodeType.CLASS: 1.6,
                NodeType.MODULE: 1.4,
                NodeType.PATTERN: 1.3,
                NodeType.DECISION: 1.1,
                NodeType.VAULT_CONCEPT: 0.9,
            },
            TaskType.OPTIMIZATION: {
                NodeType.FUNCTION: 1.8,
                NodeType.FILE: 1.4,
                NodeType.PATTERN: 1.2,
            },
            TaskType.DEBUG_TRACE: {
                NodeType.FUNCTION: 1.8,
                NodeType.FILE: 1.5,
                NodeType.CLASS: 1.3,
                NodeType.CONFIG: 1.1,
            },
            TaskType.ANALYSIS: {},
            TaskType.ARCHITECTURE_REVIEW: {
                NodeType.MODULE: 1.7,
                NodeType.DECISION: 1.5,
                NodeType.PATTERN: 1.4,
                NodeType.FILE: 1.1,
            },
        }.get(task_type, {})

    @staticmethod
    def _text_match(node, terms) -> float:
        """Fraction of query terms present in the node's own text.

        A term counts as a hit anywhere in the haystack (name, path, or the
        property values), so "staging" matches a file called duckdb_backend.py
        only if the word is actually recorded on it — not because the file is
        central. Weighted by term length so a rare word outranks a common one.
        """
        haystack = " ".join(
            [
                node.label or "",
                # file_path is recorded in metadata by the indexer, not in
                # properties — reading only properties matched nothing.
                str(node.metadata.get("file_path", "")),
                str(node.properties.get("file_path", "")),
            ]
            + [
                str(v)
                for source in (node.metadata, node.properties)
                for v in source.values()
                if isinstance(v, (str, int, float))
            ]
        ).lower()
        if not haystack:
            return 0.0
        hits = 0.0
        for term in terms:
            if not term:
                continue
            if term in haystack:
                hits += 1.0 + min(len(term), 12) / 12.0
        return hits / max(sum(1.0 + min(len(t), 12) / 12.0 for t in terms if t), 1e-9)

    def rank(self, node_ids, task_analysis=None, terms=None):
        scored = [(nid, self.score(nid, task_analysis, terms)) for nid in node_ids]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored
