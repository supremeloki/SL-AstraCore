from collections import defaultdict, deque
from astra.core.logger import get_logger
from astra.models.graph_node import NodeType

logger = get_logger("astra.context.graph_query")

# Words too generic to stem-match on: they would flood every query.
_STEM_STOPWORDS = frozenset({"a", "an", "the", "is", "are", "in", "of", "to", "and", "or", "it", "this"})


def _light_stem(word):
    """Crude suffix stripper: enough to bridge 'indexing' and 'index'.

    Deliberately tiny — a real stemmer pulls in nltk and is not worth the weight
    for a local single-user tool. Only the query word is stemmed, so identifier
    boundaries in the index are never mangled.
    """
    if len(word) <= 4 or word in _STEM_STOPWORDS:
        return ""
    for suffix in ("ing", "ed"):
        if word.endswith(suffix):
            base = word[: -len(suffix)]
            if len(base) < 3:
                return ""
            # 'running' -> 'runn' -> 'run': collapse a doubled final consonant.
            if len(base) > 3 and base[-1] == base[-2] and base[-1] not in "aeiou":
                base = base[:-1]
            return base
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("sses") or word.endswith("shes") or word.endswith("ches"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 4:
        return word[:-1]
    return ""


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
            # A file's own vocabulary, not just its name. Seeds come from
            # find_by_keyword, so with only names in this index a question
            # about what a file does found one candidate: the file whose name
            # happened to contain a query word. "how does the access token
            # guard api calls" seeded token_budget.py and nothing else.
            if node.node_type == NodeType.FILE:
                source_terms = node.properties.get("source_terms")
                if source_terms is None:
                    from astra.context.file_terms import file_terms

                    path = str(node.properties.get("file_path", ""))
                    source_terms = file_terms(path) if path else set()
                    node.properties["source_terms"] = source_terms
                tokens.update(source_terms)
            for token in tokens:
                self._label_index.setdefault(token, set()).add(node.id)

    def find_by_keyword(self, keyword):
        """Substring match, plus a light stem so 'indexing' finds 'index_repo'.

        A user asking "how does indexing work" should not have to know whether
        the code calls it index_repo, indexing, or index. Only the query word is
        stemmed; indexed tokens are compared as-is so precision is preserved.
        """
        kw = keyword.lower()
        stem = _light_stem(kw)
        matches = set()
        for token, ids in self._label_index.items():
            if kw in token or (stem and (stem in token or token in stem)):
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
