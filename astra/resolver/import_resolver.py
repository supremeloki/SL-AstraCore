from __future__ import annotations

import os
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
    root_prefix = _common_root(parse_results)
    module_to_file: dict[str, str] = {}
    file_to_module: dict[str, str] = {}

    for result in parse_results:
        if not result.file_node:
            continue
        fp = result.file_node.file_path
        rel_fp = _relativize(fp, root_prefix)
        file_path = Path(rel_fp)

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
                dep, _relativize(src_fp, root_prefix), module_to_file, file_to_module,
                parsed_files={_relativize(r.file_node.file_path, root_prefix) for r in parse_results if r.file_node},
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


def _common_root(parse_results: Sequence[IRFileParseResult]) -> str | None:
    paths: list[Path] = []
    for r in parse_results:
        if r.file_node and Path(r.file_node.file_path).is_absolute():
            paths.append(Path(r.file_node.file_path))
    if len(paths) < 2:
        return None
    try:
        common = Path(os.path.commonpath([str(p) for p in paths]))
    except ValueError:
        return None
    if common == common.anchor or common.name == "":
        return None
    parts = common.parts
    if any(p in ("node_modules", ".venv", "venv", "__pycache__") for p in parts):
        return None
    return str(common)


def _relativize(fp: str, root_prefix: str | None) -> str:
    if root_prefix is None:
        return fp
    p = Path(fp)
    if p.is_absolute():
        try:
            return p.relative_to(root_prefix).as_posix()
        except ValueError:
            return fp
    return fp


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