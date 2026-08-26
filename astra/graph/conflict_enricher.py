from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from astra.ir.models import IRDependency, IRFileNode


@dataclass(frozen=True)
class ConflictMatch:
    source_a: str
    source_b: str
    category: str
    severity: str
    confidence: float
    description: str


def detect_naming_conflicts(files: Sequence[IRFileNode]) -> Sequence[ConflictMatch]:
    name_map: dict[str, list[IRFileNode]] = defaultdict(list)

    for node in files:
        stem = node.file_path.replace("\\", "/").split("/")[-1]
        base = stem.split(".")[0]
        # ponytail: __init__/setup-style magic names collide by design in every
        # package — flagging them is pure noise; revisit if a real signal emerges.
        if base.lower() in ("__init__", "setup", "conftest", "index"):
            continue
        name_map[base.lower()].append(node)

    conflicts = []

    for name, nodes in name_map.items():
        if len(nodes) < 2:
            continue
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if _different_modules(nodes[i].file_path, nodes[j].file_path):
                    conflicts.append(ConflictMatch(
                        source_a=nodes[i].file_path,
                        source_b=nodes[j].file_path,
                        category="naming",
                        severity="low",
                        confidence=0.8,
                        description=f"same base name '{name}' in different modules",
                    ))

    return sorted(conflicts, key=lambda c: (c.source_a, c.source_b))


def detect_circular_dependencies(deps: Sequence[IRDependency]) -> Sequence[ConflictMatch]:
    graph: dict[str, set[str]] = defaultdict(set)

    for dep in deps:
        target = dep.resolved_target or dep.target_module
        if dep.source_file and target:
            graph[dep.source_file].add(target)

    conflicts = []
    seen_cycles: set[tuple[str, ...]] = set()

    visited: set[str] = set()
    stack: set[str] = set()

    def _dfs(node: str, path: list[str]) -> None:
        if node in stack:
            cycle_start = path.index(node)
            cycle = tuple(path[cycle_start:] + [node])
            cycle_canonical = tuple(sorted(cycle[:-1]))
            if cycle_canonical not in seen_cycles:
                seen_cycles.add(cycle_canonical)
                conflicts.append(ConflictMatch(
                    source_a=cycle[0],
                    source_b=cycle[-2],
                    category="circular_dependency",
                    severity="high",
                    confidence=0.9,
                    description=f"circular dependency: {' -> '.join(cycle[:5])}",
                ))
            return
        if node in visited:
            return

        visited.add(node)
        stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, set()):
            _dfs(neighbor, path)

        path.pop()
        stack.remove(node)

    for node in list(graph.keys()):
        visited = set()
        stack = set()
        _dfs(node, [])

    return sorted(conflicts, key=lambda c: c.description)


def _different_modules(path_a: str, path_b: str) -> bool:
    parts_a = path_a.replace("\\", "/").split("/")
    parts_b = path_b.replace("\\", "/").split("/")
    return parts_a[:-1] != parts_b[:-1]
