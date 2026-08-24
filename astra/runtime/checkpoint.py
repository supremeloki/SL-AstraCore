from __future__ import annotations

import json
import os
from typing import Any

class CheckpointManager:
    """Persists runtime state snapshots for crash recovery."""

    def __init__(self, checkpoint_dir: str) -> None:
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)

    def save(self, checkpoint_id: str, state: Any) -> str:
        path = os.path.join(self.checkpoint_dir, f"{checkpoint_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f)
        return path

    def load(self, checkpoint_id: str) -> Any:
        path = os.path.join(self.checkpoint_dir, f"{checkpoint_id}.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
