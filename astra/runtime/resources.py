from __future__ import annotations

import os
import psutil
from dataclasses import dataclass
from typing import Optional


@dataclass
class ResourceQuota:
    max_cpu_percent: float = 50.0
    max_memory_mb: float = 512.0
    max_execution_seconds: float = 300.0


class ResourceManager:
    """Resource-aware execution with CPU/memory/time quotas."""

    def __init__(self) -> None:
        self._process = psutil.Process(os.getpid())
        self._active_quotas: dict[str, ResourceQuota] = {}

    def assign_quota(self, task_id: str, quota: ResourceQuota) -> None:
        self._active_quotas[task_id] = quota

    def release_quota(self, task_id: str) -> None:
        self._active_quotas.pop(task_id, None)

    def current_memory_mb(self) -> float:
        return self._process.memory_info().rss / 1024 / 1024

    def current_cpu_percent(self) -> float:
        return self._process.cpu_percent(interval=0.1)

    def can_accept_task(self, quota: ResourceQuota) -> tuple[bool, str]:
        """Check if system has enough resources for a new task."""
        mem_used = self.current_memory_mb()
        if mem_used + quota.max_memory_mb > get_total_memory_mb():
            return False, f"Memory: {mem_used:.0f}MB used, {quota.max_memory_mb}MB requested"
        if self.current_cpu_percent() + quota.max_cpu_percent > 95.0:
            return False, "CPU near capacity"
        return True, ""

    def enforce_timeout(self, task_id: str, elapsed: float) -> bool:
        """Returns True if timeout exceeded."""
        quota = self._active_quotas.get(task_id)
        if quota and elapsed > quota.max_execution_seconds:
            return True
        return False

    def enforce_memory(self, task_id: str) -> tuple[bool, str]:
        """Returns False if memory quota exceeded."""
        quota = self._active_quotas.get(task_id)
        if quota and self.current_memory_mb() > quota.max_memory_mb:
            return False, f"Memory limit {quota.max_memory_mb}MB exceeded"
        return True, ""


def get_total_memory_mb() -> float:
    """System total memory in MB."""
    mem = psutil.virtual_memory()
    return mem.total / 1024 / 1024