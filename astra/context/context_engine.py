from astra.core.logger import get_logger
from astra.core.lifecycle import Lifecycle
from astra.models.context_pack import ContextPack
from astra.models.dependency_snapshot import DependencySnapshot, RiskSummary
from astra.context.task_analyzer import TaskAnalyzer
from astra.context.graph_query import GraphQuery
from astra.context.ranking import Ranking
from astra.context.token_budget import TokenBudget
from astra.context.strategy_engine import StrategyEngine
from astra.context.context_selector import ContextSelector

logger = get_logger("astra.context.context_engine")


class ContextEngine:
    def __init__(self, knowledge_graph):
        self._kg = knowledge_graph
        self._task_analyzer = TaskAnalyzer()
        self._graph_query = GraphQuery(knowledge_graph)
        self._ranking = Ranking(knowledge_graph)
        self._token_budget = TokenBudget()
        self._strategy_engine = StrategyEngine()
        self._selector = ContextSelector(self._graph_query, self._ranking)
        self._lifecycle = Lifecycle()

    def build_pack(self, task_text):
        logger.info("Phase 4 started: context building for '%s'", task_text[:60])
        self._lifecycle.advance("reading")

        task_analysis = self._task_analyzer.analyze(task_text)
        logger.info(
            "Task: type=%s domain=%s keywords=%d confidence=%.2f",
            task_analysis.task_type.value,
            task_analysis.affected_domain,
            len(task_analysis.keywords),
            task_analysis.confidence,
        )

        self._lifecycle.advance("parsing")
        strategy = self._strategy_engine.get_strategy(task_analysis.task_type)()
        logger.info("Strategy: %s (max_nodes=%d)", task_analysis.task_type.value, strategy["max_nodes"])

        self._lifecycle.advance("semantic_tagging")
        pack, deps, risks = self._selector.select(task_analysis, strategy)
        self._enforce_token_budget(pack)

        self._lifecycle.advance("index_output")
        self._validate(pack)

        self._lifecycle.advance("complete")
        logger.info(
            "Phase 4 complete: nodes=%d files=%d concepts=%d conflicts=%d tokens=%d",
            len(pack.relevant_nodes),
            len(pack.required_files),
            len(pack.relevant_concepts),
            len(pack.conflicts_to_watch),
            pack.token_estimate,
        )

        return task_analysis, pack, deps, risks

    def _enforce_token_budget(self, pack):
        budget = self._token_budget
        # Budget state is per-pack: without this reset a long-lived engine
        # instance accumulates used across calls until packs silently starve.
        budget.reset()

        def node_cost(n):
            text = f"{n['id']} {n['label']} {n['type']}"
            return budget.estimate(text)

        seeds = set(pack.metadata.get("seed_ids", ()))
        kept = []
        dropped = False
        # Seeds are reserved unconditionally; non-seeds fill the remaining budget.
        for n in pack.relevant_nodes:
            if not dropped and (n["id"] in seeds or budget.can_fit(f"{n['id']} {n['label']} {n['type']}")):
                budget.reserve(n["id"], f"{n['id']} {n['label']} {n['type']}", force=n["id"] in seeds)
                kept.append(n)
            else:
                dropped = True
        if dropped:
            logger.info("Token budget: dropped %d low-relevance node(s)", len(pack.relevant_nodes) - len(kept))
        pack.relevant_nodes = kept
        pack.required_files = [f for f in pack.required_files if any(
            n.get("file_path") == f or f in n.get("file_path", "") for n in kept
        )] if kept else []
        pack.token_estimate = sum(node_cost(n) for n in kept)

    def _estimate_tokens(self, pack):
        self._token_budget.reset()
        for node in pack.relevant_nodes:
            text = f"{node['id']} {node['label']} {node['type']}"
            self._token_budget.reserve(node["id"], text, force=True)
        for f in pack.required_files:
            self._token_budget.reserve(f, f, force=True)
        for c in pack.critical_dependencies:
            self._token_budget.reserve(str(c), str(c), force=True)
        return self._token_budget.used

    def _validate(self, pack):
        seen = set()
        deduped = []
        for node in pack.relevant_nodes:
            if node["id"] not in seen:
                seen.add(node["id"])
                deduped.append(node)
        pack.relevant_nodes = deduped
        pack.required_files = sorted(set(pack.required_files))
        pack.relevant_concepts = list(set(pack.relevant_concepts))
        pack.conflicts_to_watch = list(set(pack.conflicts_to_watch))
