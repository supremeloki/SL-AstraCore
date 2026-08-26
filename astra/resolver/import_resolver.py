from __future__ import annotations

import os
import posixpath
from pathlib import Path
from typing import Sequence

from astra.ir.models import (
    EdgeType,
    IREdge,
    IRDependency,
    IRFileParseResult,
)

_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


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
    parsed_files: dict[str, str] = {
        _relativize(r.file_node.file_path, root_prefix): r.file_node.file_path
        for r in parse_results
        if r.file_node
    }

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
        rel_src = _relativize(src_fp, root_prefix)

        for dep in result.dependencies:
            resolved_path = _resolve_one_import(
                dep, rel_src, module_to_file, file_to_module, parsed_files,
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
    # Single-directory repo: bump root one level up so intra-package imports
    # (e.g. "pkg.helpers") keep their package qualifier in relative paths.
    if all(p.parent == common for p in paths):
        common = common.parent
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
    parsed_files: dict[str, str],
) -> str | None:
    target = dep.target_module

    if target in parsed_files:
        return parsed_files[target]

    if target in module_to_file:
        return module_to_file[target]

    source_dir = posixpath.dirname(source_file)

    if target.startswith(("./", "../")):
        return _resolve_js_relative(target, source_dir, parsed_files)

    if target.startswith(".") or dep.level > 0:
        return _resolve_python_relative(dep, source_dir, module_to_file, parsed_files)

    base = posixpath.normpath(posixpath.join(source_dir, target.replace(".", "/")))
    for cand in (f"{base}.py", f"{base}/__init__.py"):
        if cand in parsed_files:
            return cand

    return None


def _resolve_python_relative(
    dep: IRDependency,
    source_dir: str,
    module_to_file: dict[str, str],
    parsed_files: dict[str, str],
) -> str | None:
    target = dep.target_module
    n_dots = len(target) - len(target.lstrip("."))
    level = n_dots or dep.level or 1
    rest = target.lstrip(".")

    parts = [p for p in source_dir.split("/") if p and p != "."]
    up = level - 1
    if up > len(parts):
        return None
    base_parts = parts[: len(parts) - up]
    base = "/".join(base_parts)

    if not rest:
        init = f"{base}/__init__.py" if base else "__init__.py"
        return parsed_files.get(init)

    mod_path = f"{base}/{rest.replace('.', '/')}" if base else rest.replace(".", "/")
    for cand in (f"{mod_path}.py", f"{mod_path}/__init__.py"):
        if cand in parsed_files:
            return parsed_files[cand]

    mod = f"{base}.{rest}" if base else rest
    if mod in module_to_file:
        return module_to_file[mod]
    return None


def _resolve_js_relative(target: str, source_dir: str, parsed_files: dict[str, str]) -> str | None:
    base = posixpath.normpath(posixpath.join(source_dir, target))
    if base in parsed_files:
        return parsed_files[base]
    for ext in _JS_EXTS:
        cand = f"{base}{ext}"
        if cand in parsed_files:
            return parsed_files[cand]
    for ext in _JS_EXTS:
        cand = f"{base}/index{ext}"
        if cand in parsed_files:
            return parsed_files[cand]
    return None
