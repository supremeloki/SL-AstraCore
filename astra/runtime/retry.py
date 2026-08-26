from __future__ import annotations

import inspect
import asyncio
import time
import random
import logging
from typing import Callable, TypeVar, ParamSpec, Optional

T = TypeVar("T")
P = ParamSpec("P")

logger = logging.getLogger("astra.runtime.retry")


class RetryOrchestrator:
    """Orchestrates resilient execution with exponential backoff and jitter."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: bool = True,
        retryable_exceptions: tuple[type[BaseException], ...] = (Exception,),
    ) -> None:
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions

    def _compute_delay(self, attempt: int) -> float:
        delay = self.base_delay * (2 ** attempt)
        if self.jitter:
            delay *= random.uniform(0.5, 1.5)
        return min(delay, self.max_delay)

    def execute(self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        last_exc: Optional[BaseException] = None
        for attempt in range(self.max_attempts):
            try:
                return func(*args, **kwargs)
            except self.retryable_exceptions as exc:
                last_exc = exc
                if attempt == self.max_attempts - 1:
                    logger.error("Retry exhausted after %d attempts", self.max_attempts)
                    raise
                delay = self._compute_delay(attempt)
                logger.warning(
                    "Attempt %d/%d failed: %s. Retrying in %.2fs",
                    attempt + 1, self.max_attempts, exc, delay
                )
                time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    async def execute_async(self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        last_exc: Optional[BaseException] = None
        for attempt in range(self.max_attempts):
            try:
                result = func(*args, **kwargs)
                if inspect.isawaitable(result):
                    return await result
                return result  # pragma: no cover - sync callable passed to async path
            except self.retryable_exceptions as exc:
                last_exc = exc
                if attempt == self.max_attempts - 1:
                    logger.error("Retry exhausted after %d attempts", self.max_attempts)
                    raise
                delay = self._compute_delay(attempt)
                logger.warning(
                    "Async attempt %d/%d failed: %s. Retrying in %.2fs",
                    attempt + 1, self.max_attempts, exc, delay
                )
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc
