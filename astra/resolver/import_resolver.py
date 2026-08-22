from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Sequence

from astra.ir.models import (
    EdgeType,
    IREdge,
    IRDependency,
    IRFileNode,
    IRFileParseResult,
    IRSymbol,
)


def resolve_imports_into_edges(
    parse_results: Sequence[IRFileParseResult],
) -> tuple[dict[str, str], Sequence[IREdge]]:
    """
    Resolve import strings to concrete file paths and generate canonical dependency edges.

    Returns:
        (resolved_imports_map, dependency_edges)
    """
    module_to_file: dict[str, str] = {}
    file_to_module: dict[str, str] = {}

    for result in parse_results:
        if not result.file_node:
            continue
        fp = result.file_node.file_path
        file_path = Path(fp)

        stem = file_path.stem
        parent = file_path.parent.as_posix()

        file_to_module[fp] = safe_module(parent, stem)

        abs_module = safe_module(parent, stem)
        module_to_file[abs_module] = fp
        module_to_file[stem] = fp

        parts = abs_module.split(".")
        for i in range(1, len(parts) + 1):
            module_to_file[".".join(parts[:i])] = fp

    resolved_imports: dict[str, str] = {}
    dep_edges: list[IREdge] = []

    for result in parse_results:
        if not result.file_node:
            continue
        src_fp = result.file_node.file_path

        for dep in result.dependencies:
            resolved_path = _resolve_one_import(
                dep, src_fp, module_to_file, file_to_module, parsed_files={r.file_node.file_path for r in parse_results if r.file_node}
            )
            resolved_imports[dep.target_module] = resolved_path or ""

            if resolved_path:
                dep_edges.append(
                    IREdge(
                        from_node=src_fp,
                        to_node=resolved_path,
                        type=EdgeType.IMPORTS,
                        weight=1.0,
                        confidence=0.9,
                        metadata={
                            "line": dep.line,
                            "import_str": dep.target_module,
                        },
                    )
                )

    return resolved_imports, tuple(dep_edges)


def safe_module(parent: str, stem: str) -> str:
    parent_clean = parent.replace("/", ".").replace("\\", ".").strip(".")
    if parent_clean:
        return f"{parent_clean}.{stem}"
    return stem


def _resolve_one_import(
    dep: IRDependency,
    source_file: str,
    module_to_file: dict[str, str],
    file_to_module: dict[str, str],
    parsed_files: set[str],
) -> str | None:
    target = dep.target_module

    if target in parsed_files:
        return target

    if target in module_to_file:
        return module_to_file[target]

    source_dir = str(Path(source_file).parent.as_posix())

    relative_path = f"{source_dir}/{target.replace('.', '/')}.py"
    if relative_path in parsed_files:
        return relative_path

    second_path = f"{source_dir}/{target.replace('.', '/')}/__init__.py"
    if second_path in parsed_files:
        return second_path

    return None