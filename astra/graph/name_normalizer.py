from __future__ import annotations

import re
from collections import defaultdict


class NameNormalizer:
    """Canonical name normalization for IR nodes and edges."""

    _SEP_RE = re.compile(r"[_\-\s.]+")

    def normalize_key(self, name: str) -> str:
        return self._SEP_RE.sub("", name.lower())

    def normalize_path(self, path: str) -> str:
        """Normalize a file path to canonical forward-slash form."""
        cleaned = path.replace("\\", "/").strip("/")
        parts = [p for p in cleaned.split("/") if p and p not in (".", "..")]
        return "/".join(parts)

    def build_alias_map(self, entities: dict[str, list[str]]) -> dict[str, list[str]]:
        normalized: dict[str, list[str]] = defaultdict(list)
        for name, values in entities.items():
            normalized[self.normalize_key(name)].extend(values)
        return {key: values for key, values in normalized.items() if len(values) > 1}

    def normalize_node_id(self, source: str, name: str) -> str:
        """Build a canonical node ID: source::normalizedName."""
        return f"{source}::{self.normalize_key(name)}"
