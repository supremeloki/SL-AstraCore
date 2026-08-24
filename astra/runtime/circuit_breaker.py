from __future__ import annotations

import time
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Failure-domain isolation via circuit breaker."""

    def __init__(self, failure_threshold: int = 3, reset_timeout: float = 5.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.failure_count += 1
        self.success_count = 0
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def record_success(self) -> None:
        self.success_count += 1
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN and self.success_count >= 2:
            self.state = CircuitState.CLOSED
        elif self.state == CircuitState.CLOSED:
            pass  # Stay closed

    def allow(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0  # Reset success count for half-open trial
                return True
            return False
        # HALF_OPEN
        return True

    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    def is_half_open(self) -> bool:
        return self.state == CircuitState.HALF_OPEN