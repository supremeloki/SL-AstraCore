from __future__ import annotations

import cProfile
import pstats
import io
from contextlib import contextmanager
from typing import Optional
from dataclasses import dataclass
import time


@dataclass
class ProfileResult:
    total_calls: int
    total_time: float
    top_functions: list[dict]


class Profiler:
    """Lightweight profiling hooks for execution analysis."""

    def __init__(self) -> None:
        self._profiler: Optional[cProfile.Profile] = None
        self._enabled = False

    def enable(self) -> None:
        if not self._enabled:
            self._profiler = cProfile.Profile()
            self._profiler.enable()
            self._enabled = True

    def disable(self) -> Optional[ProfileResult]:
        if not self._enabled or not self._profiler:
            return None
        self._profiler.disable()
        self._enabled = False
        return self._analyze()

    def _analyze(self) -> ProfileResult:
        assert self._profiler is not None
        stream = io.StringIO()
        stats = pstats.Stats(self._profiler, stream=stream).sort_stats("cumulative")
        stats.print_stats(20)
        # Approximate total calls from stats
        total_calls = sum(stat[0] for stat in stats.stats.values())
        total_time = sum(stat[2] for stat in stats.stats.values())
        return ProfileResult(
            total_calls=total_calls,
            total_time=total_time,
            top_functions=[]
        )

    @contextmanager
    def profile(self, name: str = ""):
        """Context manager for profiling a code block."""
        self.enable()
        start = time.time()
        try:
            yield
        finally:
            result = self.disable()
            elapsed = time.time() - start
            if result:
                result.total_time = elapsed


_profiler: Optional[Profiler] = None


def get_profiler() -> Profiler:
    global _profiler
    if _profiler is None:
        _profiler = Profiler()
    return _profiler


def enable_profiling() -> None:
    get_profiler().enable()


def disable_profiling() -> Optional[ProfileResult]:
    return get_profiler().disable()