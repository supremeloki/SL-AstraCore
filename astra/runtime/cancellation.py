from __future__ import annotations

import contextvars
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Optional

_cancel_ctx: contextvars.ContextVar[Optional["CancellationContext"]] = contextvars.ContextVar("_cancel_ctx", default=None)


@dataclass
class CancellationContext:
    """Context for cancellation propagation."""
    cancelled: bool = False
    reason: str = ""
    children: list["CancellationContext"] = field(default_factory=list)
    parent: Optional["CancellationContext"] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def cancel(self, reason: str = "") -> None:
        with self._lock:
            if not self.cancelled:
                self.cancelled = True
                self.reason = reason
                # Propagate to children
                for child in self.children:
                    child.cancel(reason)

    def check(self) -> None:
        """Raise if cancelled."""
        if self.cancelled:
            raise CancelledError(f"Operation cancelled: {self.reason}")

    def __enter__(self) -> "CancellationContext":
        self._token = _cancel_ctx.set(self)
        return self

    def __exit__(self, *args) -> None:
        _cancel_ctx.reset(self._token)


class CancelledError(Exception):
    """Raised when operation is cancelled."""
    pass


def get_current_context() -> Optional[CancellationContext]:
    """Get the current cancellation context."""
    return _cancel_ctx.get()


@contextmanager
def cancellation_scope(reason: str = "") -> Iterator[CancellationContext]:
    """Create a new cancellation scope."""
    parent = get_current_context()
    ctx = CancellationContext(parent=parent)
    if parent:
        with parent._lock:
            parent.children.append(ctx)
    token = _cancel_ctx.set(ctx)
    try:
        yield ctx
    finally:
        _cancel_ctx.reset(token)


def cancel_all(reason: str = "") -> None:
    """Cancel all contexts in the current hierarchy."""
    ctx = get_current_context()
    while ctx:
        ctx.cancel(reason)
        ctx = ctx.parent


@contextmanager
def timeout_scope(seconds: float, reason: str = "Timeout") -> Iterator[CancellationContext]:
    """Context manager that cancels after timeout."""
    ctx = CancellationContext()
    timer = threading.Timer(seconds, ctx.cancel, args=[reason])
    token = _cancel_ctx.set(ctx)
    timer.start()
    try:
        yield ctx
    finally:
        timer.cancel()
        _cancel_ctx.reset(token)