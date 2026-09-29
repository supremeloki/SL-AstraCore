from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from astra.context.engine import ContextEngine
from astra.ir.models import IRContextPack


@dataclass
class CachedContext:
    key: str
    pack: IRContextPack
    created_at: float = field(default_factory=time.time)
    hits: int = 0


class ContextCache:
    """In-memory context cache with deterministic keys and TTL support."""

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 128) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._cache: dict[str, CachedContext] = {}

    def make_key(
        self,
        query_intent: str,
        seed_nodes: list[str],
        max_tokens: int | None,
    ) -> str:
        payload = {
            "query": query_intent,
            "seeds": sorted(seed_nodes),
            "max_tokens": max_tokens,
        }
        raw = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[IRContextPack]:
        item = self._cache.get(key)
        if not item:
            return None

        if (time.time() - item.created_at) > self._ttl:
            self._cache.pop(key, None)
            return None

        item.hits += 1
        return item.pack

    def put(self, key: str, pack: IRContextPack) -> None:
        if len(self._cache) >= self._max_entries:
            oldest = min(self._cache.values(), key=lambda x: x.created_at)
            self._cache.pop(oldest.key, None)

        self._cache[key] = CachedContext(key=key, pack=pack)

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

    def stats(self) -> dict[str, int]:
        return {
            "entries": len(self._cache),
            "max_entries": self._max_entries,
        }


class ContextRetrievalEngine:
    """Retrieval runtime over ContextEngine + ContextCache."""

    def __init__(
        self,
        context_engine: ContextEngine,
        cache: Optional[ContextCache] = None,
    ) -> None:
        self._engine = context_engine
        self._cache = cache or ContextCache()

    def retrieve(
        self,
        query_intent: str,
        seed_nodes: list[str],
        max_tokens: int | None = None,
        use_cache: bool = True,
    ) -> IRContextPack:
        key = self._cache.make_key(query_intent, seed_nodes, max_tokens)

        if use_cache:
            cached = self._cache.get(key)
            if cached:
                return cached

        pack = self._engine.generate_context_pack(
            query_intent=query_intent,
            seed_nodes=seed_nodes,
            max_tokens=max_tokens,
        )

        if use_cache:
            self._cache.put(key, pack)

        return pack
