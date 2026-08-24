from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass
class DeadLetterItem:
    reason: str
    payload: Any

class DeadLetterQueue:
    """Stores permanently failed runtime tasks."""

    def __init__(self) -> None:
        self._items: list[DeadLetterItem] = []

    def push(self, reason: str, payload: Any) -> None:
        self._items.append(DeadLetterItem(reason=reason, payload=payload))

    def list(self) -> list[DeadLetterItem]:
        return list(self._items)
