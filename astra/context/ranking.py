from astra.context.stemming import name_stems, stem, stem_set
from astra.core.logger import get_logger
from astra.models.graph_node import NodeType
from astra.models.task_analysis import TaskType

logger = get_logger("astra.context.ranking")

# Reading and tokenising every source file is the expensive part of scoring, and
# the answer only changes when the file does. Cached by path for the process,
# because the KnowledgeGraph is rebuilt per query and its node objects are
# thrown away each time.
_SOURCE_TERMS_CACHE: dict = {}
_SOURCE_TERMS_CACHE_LIMIT = 4096

# Node types that describe the repo rather than its code.
_ANALYTIC_TYPES = (NodeType.PATTERN, NodeType.CONFLICT, NodeType.DECISION)

# The weight table depends only on the task type, never on the node, so it is
# safe to share across Ranking instances.
_TYPE_WEIGHT_CACHE: dict = {}


def _degree(count: int) -> float:
    """log1p so a hub with 178 edges is not 30x a file with 6."""
    import math

    return math.log1p(count)


def _is_test_file(node) -> bool:
    path = str(node.metadata.get("file_path", "") or node.properties.get("file_path", ""))
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    stem = name[:-3] if name.endswith(".py") else name
    # Match on the stem, not the suffix: endswith("test.py") also matched
    # contest.py and attestation.py.
    return stem.startswith("test_") or stem.endswith("_test")


class Ranking:
    def __init__(self, knowledge_graph, document_frequency=None, files_indexed=None):
        self._kg = knowledge_graph
        self._adj = {}
        self._reverse_adj = {}
        self._build()
        if document_frequency is not None:
            self._document_frequency = document_frequency
            self._files_indexed = files_indexed or 1
        else:
            self._document_frequency = self._compute_document_frequency()
            self._files_indexed = self._count_files()
        self._exact_symbol_names: frozenset = frozenset()

    def _count_files(self) -> int:
        return sum(
            1 for n in self._kg.node_index.values() if n.node_type == NodeType.FILE
        ) or 1

    def _compute_document_frequency(self) -> dict:
        """How many files contain each stem, across the graph.

        A word every file has is not evidence. Without this the biggest module
        in the repo won every question simply by containing more distinct
        words than the one that is actually about the subject.
        """
        frequency: dict[str, int] = {}
        for node in self._kg.node_index.values():
            if node.node_type != NodeType.FILE:
                continue
            terms = self._source_terms_of(node)
            if not terms:
                continue
            for bucket in {stem(t) for t in terms}:
                frequency[bucket] = frequency.get(bucket, 0) + 1
        return frequency

    def carried_over(self) -> tuple:
        """The document frequency, for reuse when this Ranking is replaced.

        The orchestrator rebuilds the KnowledgeGraph for every query, and
        recomputing the counts re-walked 200 files each time, which is what
        turned a 120ms query into a second.
        """
        return self._document_frequency, self._files_indexed

    def _idf(self, stem: str) -> float:
        """Inverse document frequency, floored so a unique word is not infinite."""
        import math

        seen = self._document_frequency.get(stem, 0)
        return math.log((self._files_indexed + 1) / (seen + 1)) + 1.0

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
            match = self._text_match(node, terms)
            if _is_test_file(node):
                # A test is *about* the subject, which makes it a better lexical
                # match than the implementation — so the penalty has to apply to
                # the text term too, not just the structural part.
                match *= 0.3
            score += 15.0 * match

        structural = 0.0
        structural += node.confidence * 1.5
        # Degree is logarithmic and capped. Linear weighting made one hub file
        # unbeatable: models.py has 88 edges and 0.4 each is 35 points, which
        # no amount of text matching could overcome, so it came first for every
        # question regardless of the question.
        structural += min(_degree(self._adj.get(node_id, 0)), 6.0) * 0.5
        structural += min(_degree(self._reverse_adj.get(node_id, 0)), 6.0) * 0.6
        if _is_test_file(node):
            # A test that exercises the answer is not the answer. An agent
            # reading a context pack needs the implementation; the test ranks
            # above it purely because its name repeats the query words.
            structural *= 0.25
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
            # A file is the unit an agent navigates by. Prefer it over the
            # symbols inside other files that merely share a word with the
            # query: given "what resolves imports", the answer is
            # import_resolver.py, not whichever helper happens to be called
            # find_imports.
            #
            # A file whose own name answers the question gets a much larger
            # bonus. orchestrator.py contains "nodes", "ranked" and "relevance"
            # somewhere in 600 lines; ranking.py is the module about ranking.
            # One matching word is enough, because a name is a label for the
            # whole file and the other question words are what it is for.
            # Withdrawn when a symbol is named exactly the question: asked for
            # resolve_imports_into_edges, that function is the answer and the
            # file containing it is not.
            if self._symbol_answers_exactly(terms):
                score += 1.5
            else:
                score += 9.0 if self._name_answers(node, terms) else 1.5
        elif node_type == NodeType.CLASS:
            score += 0.7
        elif node_type == NodeType.FUNCTION:
            # A private helper inherits the vocabulary of the file it lives in,
            # so every method of ranking.py matched the question "how does
            # ranking work" and thirteen of them filled the pack. Their own name
            # has to earn the place, not their file's.
            score += 0.6
        elif node_type == NodeType.VAULT_CONCEPT:
            score += 0.4
        if node_type in (NodeType.FUNCTION, NodeType.CLASS) and terms:
            own = name_stems((node.label or "").replace(".py", ""))
            if not (stem_set(terms) & own):
                score *= 0.3
        if node_type in _ANALYTIC_TYPES:
            # The type bonus is what source gets for being source; an analytic
            # label gets none of it.
            score *= 0.2
        return round(score, 3)

    def _type_weights(self, task_type):
        # Built once per task type, not once per candidate node: this dict
        # holds a dozen entries and ranking 43 nodes was rebuilding it 43 times.
        cached = _TYPE_WEIGHT_CACHE.get(task_type)
        if cached is not None:
            return cached
        weights = self._build_type_weights(task_type)
        _TYPE_WEIGHT_CACHE[task_type] = weights
        return weights

    def _build_type_weights(self, task_type):
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

    def _text_match(self, node, terms) -> float:
        """Fraction of query terms the node's own text accounts for.

        Three sources, in descending order of authority:
          1. the file's own vocabulary, from its source (cached on the node),
          2. its name and path,
          3. analytic property values.

        Source text matters because a graph node records only a path, a
        language and a size: without the body, "what resolves imports between
        files" cannot tell import_resolver.py from any other module, since
        only one of them ever says `resolve`.
        """
        if not terms:
            return 0.0

        # Terms arrive stemmed from the indexer; stem the query to match.
        wanted = stem_set(terms)
        if not wanted:
            return 0.0
        total = sum(1.0 + min(len(t), 12) / 12.0 for t in wanted)

        source_terms = self._source_terms_of(node)
        if source_terms:
            # Coverage of the query, not raw hit count: a 600-line module has
            # more distinct words than a 40-line one, so counting hits made the
            # largest file win every question. Density is capped so a file that
            # is *about* the subject can still outrank one that merely mentions
            # the words in passing.
            #
            # Matching is on word stems, not whole words: a question says
            # "resolves" and the code says "resolve_imports", and an exact
            # comparison scored that as no match at all. The stems are indexed
            # once per file so this stays linear rather than quadratic.
            # Already stemmed when the file was indexed.
            stems = set(source_terms)
            # Weight each hit by how rare that word is across the repo. A word
            # in every file counts for little; a word in one file counts a lot.
            weighted = 0.0
            maximum = 0.0
            for term in wanted:
                maximum += self._idf(term)
                if term in stems:
                    weighted += self._idf(term)
            if maximum <= 0:
                return 0.0
            return min(1.0, weighted / maximum)

        haystack = " ".join(
            [
                node.label or "",
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
        hits = sum(1.0 + min(len(t), 12) / 12.0 for t in wanted if t in haystack)
        return hits / total

    @staticmethod
    @staticmethod
    def _name_answers(node, terms) -> bool:
        """Does the file's own name answer the question?

        "how are nodes ranked by relevance" -> ranking.py: the name carries
        "rank" and the other two words are what ranking is for. Requiring the
        whole question would exclude it, and a file that merely contains the
        words somewhere in its body would win instead.

        One shared word is not enough. token_budget.py holds "token" and so did
        dashboard_app.py, and the file named after the word beat the file that
        actually guards api calls with three more of the question's words. The
        name has to cover most of the question, or at least two of its words.
        """
        if not terms:
            return False
        wanted = stem_set(terms)
        if not wanted:
            return False
        name_terms = name_stems((node.label or "").replace(".py", ""))
        overlap = wanted & name_terms
        if not overlap:
            return False
        return len(overlap) >= 2 or len(overlap) == len(wanted)

    def _compute_exact_symbol_names(self, terms) -> frozenset:
        """Stem sets that some symbol is named exactly. Computed once per rank."""
        if not terms:
            return frozenset()
        wanted = stem_set(terms)
        if not wanted:
            return frozenset()
        for other in self._kg.node_index.values():
            if other.node_type in (NodeType.FUNCTION, NodeType.CLASS) and name_stems(
                other.label or ""
            ) == wanted:
                return frozenset({frozenset(wanted)})
        return frozenset()

    def _symbol_answers_exactly(self, terms) -> bool:
        """Is some symbol's own name exactly the question's words?

        Checked across the graph, once per rank, so this is a set membership
        test rather than a scan per node.
        """
        wanted = stem_set(terms) if terms else set()
        return bool(wanted) and frozenset(wanted) in self._exact_symbol_names

    def _source_terms_of(self, node) -> set:
        path = str(node.metadata.get("file_path", "") or node.properties.get("file_path", ""))
        if not path or node.node_type != NodeType.FILE:
            return set()
        cached = _SOURCE_TERMS_CACHE.get(path)
        if cached is not None:
            return cached
        from astra.context.file_terms import file_terms

        terms = file_terms(path)
        if len(_SOURCE_TERMS_CACHE) >= _SOURCE_TERMS_CACHE_LIMIT:
            # A runaway indexer should not grow this without bound; the cost of
            # recomputing is a file read, not a correctness problem.
            _SOURCE_TERMS_CACHE.clear()
        _SOURCE_TERMS_CACHE[path] = terms
        return terms

    def rank(self, node_ids, task_analysis=None, terms=None):
        self._exact_symbol_names = self._compute_exact_symbol_names(terms)
        scored = [(nid, self.score(nid, task_analysis, terms)) for nid in node_ids]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored
