from __future__ import annotations

from typing import Protocol, Sequence

from astra.graph.api import KnowledgeGraph
from astra.ir.models import IRContextPack, TaskType


class ContextPass(Protocol):
    name: str

    def run(self, context_pack: IRContextPack) -> IRContextPack: ...


class ContextPassRegistry(Protocol):
    def register(self, context_pass: ContextPass) -> None: ...

    def unregister(self, name: str) -> None: ...

    def passes(self) -> Sequence[ContextPass]: ...


class TaskAnalyzer(Protocol):
    def classify(self, query: str) -> TaskType: ...


class ContextSelector(Protocol):
    def select(
        self,
        graph: KnowledgeGraph,
        query: str,
    ) -> Sequence[str]: ...


class RankingEngine(Protocol):
    def rank(
        self,
        node_ids: Sequence[str],
    ) -> Sequence[str]: ...


class TokenBudgetManager(Protocol):
    def estimate(self, context_pack: IRContextPack) -> int: ...

    def enforce(self, context_pack: IRContextPack) -> IRContextPack: ...


class ContextEngine(Protocol):
    def build_pack(
        self,
        graph: KnowledgeGraph,
        query: str,
    ) -> IRContextPack: ...
