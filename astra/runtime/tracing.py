from __future__ import annotations

import contextvars
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional
import time


# Context variable for current trace/span
_current_span: contextvars.ContextVar[Optional["Span"]] = contextvars.ContextVar("_current_span", default=None)


@dataclass
class Span:
    """A single span in a distributed trace."""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    tags: dict[str, str] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)

    def finish(self) -> None:
        self.end_time = time.time()

    @property
    def duration_ms(self) -> float:
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000

    def add_tag(self, key: str, value: str) -> None:
        self.tags[key] = value

    def add_event(self, name: str, attrs: dict[str, str] | None = None) -> None:
        self.events.append({
            "timestamp": time.time(),
            "name": name,
            "attributes": attrs or {}
        })


class Tracer:
    """Distributed tracing with span correlation and context propagation."""

    def __init__(self, service_name: str = "astra-runtime") -> None:
        self.service_name = service_name
        self._spans: list[Span] = []

    def start_span(self, name: str, parent: Optional[Span] = None, tags: dict[str, str] | None = None) -> Span:
        trace_id = parent.trace_id if parent else str(uuid.uuid4())
        span = Span(
            span_id=str(uuid.uuid4()),
            trace_id=trace_id,
            parent_span_id=parent.span_id if parent else None,
            name=name,
            tags={"service": self.service_name, **(tags or {})}
        )
        self._spans.append(span)
        return span

    @contextmanager
    def trace(self, name: str, parent: Optional[Span] = None, tags: dict[str, str] | None = None):
        """Context manager for tracing a block of code."""
        span = self.start_span(name, parent, tags)
        token = _current_span.set(span)
        try:
            yield span
        except Exception as e:
            span.add_tag("error", "true")
            span.add_event("exception", {"type": type(e).__name__, "message": str(e)})
            raise
        finally:
            span.finish()
            _current_span.reset(token)

    def get_current_span(self) -> Optional[Span]:
        return _current_span.get()

    def export_spans(self) -> list[dict]:
        return [
            {
                "span_id": s.span_id,
                "trace_id": s.trace_id,
                "parent_span_id": s.parent_span_id,
                "name": s.name,
                "duration_ms": s.duration_ms,
                "tags": s.tags,
                "events": s.events,
            }
            for s in self._spans
        ]

    def reset(self) -> None:
        self._spans.clear()