from astra.core.logger import get_logger
from astra.models.graph_node import NodeType
from astra.models.task_analysis import TaskType

logger = get_logger("astra.context.ranking")


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

    def score(self, node_id, task_analysis=None):
        node = self._kg.node_index.get(node_id)
        if node is None:
            return 0.0
        score = 0.0
        score += node.confidence * 1.5
        score += self._adj.get(node_id, 0) * 0.3
        score += self._reverse_adj.get(node_id, 0) * 0.4
        if node.is_orphan:
            score *= 0.3
        risk = node.properties.get("risk", "low")
        if risk == "high":
            score += 2.0
        elif risk == "medium":
            score += 1.0
        node_type = node.node_type
        if task_analysis:
            type_weights = self._type_weights(task_analysis.task_type)
            score *= type_weights.get(node_type, 1.0)
        if node_type == NodeType.FILE:
            score += 0.5
        elif node_type == NodeType.CLASS:
            score += 0.7
        elif node_type == NodeType.FUNCTION:
            score += 0.6
        elif node_type == NodeType.VAULT_CONCEPT:
            score += 0.4
        complexity = node.properties.get("complexity", 0)
        score += min(complexity / 50.0, 1.0)
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

    def rank(self, node_ids, task_analysis=None):
        scored = [(nid, self.score(nid, task_analysis)) for nid in node_ids]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored
