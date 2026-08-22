from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from astra.ir.models import IRFileNode


@dataclass(frozen=True)
class PatternMatch:
    name: str
    confidence: float
    locations: tuple[str, ...] = ()


DESIGN_PATTERNS = {
    "repository": ["repository", "repo"],
    "factory": ["factory", "create_", "build_"],
    "observer": ["observer", "subscribe", "event"],
    "adapter": ["adapter", "wrapper"],
}

NAMING_CONVENTIONS = {
    "snake_case": re.compile(r"^[a-z][a-z0-9_]*$"),
    "PascalCase": re.compile(r"^[A-Z][a-zA-Z0-9]*$"),
}


def detect_design_patterns(files: Sequence[IRFileNode]) -> Sequence[PatternMatch]:
    counts: dict[tuple[str, str], int] = defaultdict(int)

    for node in files:
        parts = node.file_path.replace("\\", "/").split("/")
        for part in parts:
            lowered = part.lower()
            for pattern_name, signals in DESIGN_PATTERNS.items():
                if any(signal in lowered for signal in signals):
                    counts[(pattern_name, part)] += 1

    patterns = []
    for (pattern_name, signal), count in counts.items():
        if count >= 2:
            locations = tuple(
                node.file_path
                for node in files
                if signal.lower() in node.file_path.lower()
            )
            patterns.append(PatternMatch(
                name=pattern_name,
                confidence=min(count * 0.15, 0.9),
                locations=locations,
            ))

    return sorted(patterns, key=lambda p: p.name)


def detect_naming_conventions(files: Sequence[IRFileNode]) -> Sequence[PatternMatch]:
    matches = []

    for convention_name, regex in NAMING_CONVENTIONS.items():
        matching = []

        for node in files:
            stem = node.file_path.split("/")[-1].split(".")[0]
            if regex.match(stem):
                matching.append(node.file_path)

        ratio = len(matching) / len(files) if files else 0
        if ratio > 0.5:
            matches.append(PatternMatch(
                name=f"naming:{convention_name}",
                confidence=round(ratio, 2),
                locations=tuple(sorted(matching)),
            ))

    return sorted(matches, key=lambda p: p.name)
