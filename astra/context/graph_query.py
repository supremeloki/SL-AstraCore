from collections import defaultdict, deque
from astra.core.logger import get_logger
from astra.models.graph_node import NodeType

logger = get_logger("astra.context.graph_query")


class GraphQuery:
    def __init__(self, knowledge_graph):
        self._kg = knowledge_graph
        self._adj = None
        self._reverse_adj = None
        self._label_index = None
        self._build_indexes()

    def _build_indexes(self):
        self._adj = defaultdict(list)
        self._reverse_adj = defaultdict(list)
        for edge in self._kg.edges:
            self._adj[edge.from_node].append((edge.to_node, edge))
            self._reverse_adj[edge.to_node].append((edge.from_node, edge))
        self._label_index = {}
        for node in self._kg.nodes:
            label = node.label.lower()
            parts = label.replace("\\", "/").split("/")
            tokens = set()
            tokens.add(label)
            tokens.add(parts[-1])
            tokens.add(parts[-1].replace(".py", "").replace(".js", "").replace(".ts", ""))
            for part in parts:
                if part:
                    tokens.add(part.lower())
            for token in tokens:
                self._label_index.setdefault(token, set()).add(node.id)

    def find_by_keyword(self, keyword):
        kw = keyword.lower()
        matches = set()
        for token, ids in self._label_index.items():
            if kw in token:
                matches.update(ids)
        return list(matches)

    def find_by_path(self, path):
        target = path.replace("\\", "/").lower().lstrip("./")
        for node in self._kg.nodes:
            if node.node_type != NodeType.FILE:
                continue
            norm = node.label.replace("\\", "/").lower().lstrip("./")
            if norm == target or norm.endswith("/" + target) or target.endswith(norm):
                return [node.id]
        return []

    def neighbors(self, node_id, max_depth=1):
        visited = set()
        result = []
        queue = deque([(node_id, 0)])
        while queue:
            nid, depth = queue.popleft()
            if nid in visited:
                continue
            visited.add(nid)
            if depth > 0:
                result.append(nid)
            if depth >= max_depth:
                continue
            for neighbor, _ in self._adj.get(nid, []):
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))
        return result

    def upstream(self, node_id, max_depth=3):
        return self._traverse(node_id, self._reverse_adj, max_depth)

    def downstream(self, node_id, max_depth=3):
        return self._traverse(node_id, self._adj, max_depth)

    def _traverse(self, node_id, adj_map, max_depth):
        visited = {node_id: 0}
        queue = deque([node_id])
        result = []
        while queue:
            nid = queue.popleft()
            depth = visited[nid]
            if depth >= max_depth:
                continue
            for neighbor, edge in adj_map.get(nid, []):
                if neighbor not in visited:
                    visited[neighbor] = depth + 1
                    edge_type = getattr(edge, "edge_type", None) or getattr(edge, "type", None)
                    result.append((neighbor, edge_type.value if hasattr(edge_type, "value") else str(edge_type), depth + 1))
                    queue.append(neighbor)
        return result

    def related_vault_concepts(self, node_id, max_depth=2):
        related = set()
        queue = deque([(node_id, 0)])
        visited = {node_id}
        while queue:
            nid, depth = queue.popleft()
            if depth > max_depth:
                continue
            if nid.startswith("concept:"):
                related.add(nid)
            for neighbor, _edge in self._adj.get(nid, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))
        related.discard(node_id)
        return list(related)

    def find_conflicts_for(self, node_ids):
        conflicts = []
        node_set = set(node_ids)
        for conflict in self._kg.conflicts.conflicts:
            a_id = f"file:{conflict.source_a}"
            b_id = f"file:{conflict.source_b}"
            if a_id in node_set or b_id in node_set:
                conflicts.append(conflict.id)
        return conflicts

    def find_patterns_for(self, node_ids):
        patterns = []
        node_set = set(node_ids)
        for pat in self._kg.patterns.patterns:
            if any(loc in node_set for loc in pat.affects):
                patterns.append(pat.id)
        return patterns

    def get_node(self, node_id):
        return self._kg.node_index.get(node_id)

    def find_entry_points(self):
        return list(self._kg.entry_points)
