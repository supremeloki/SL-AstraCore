"""Relative-import resolution, with fixtures that are absolute on any host.

The paths here were written as _p("..."), which is absolute on Windows
and relative on Linux. _common_root gates on Path.is_absolute(), so on Linux
it dropped every fixture and these tests failed there while passing on
Windows. "/proj/..." is not the answer either: PureWindowsPath reads a
leading slash as drive-relative, so it is relative on the other host. There
is no spelling that is absolute on both, so _p builds one from the host's own
anchor and every separator comes from os.sep.
"""

import os
import time
from pathlib import Path

from astra.ir.models import (
    FileRole,
    IRDependency,
    IRFileNode,
    IRFileParseResult,
    NodeType,
)
from astra.resolver.import_resolver import resolve_imports_into_edges

# An absolute path on both hosts, without touching the filesystem. Neither
# "F:/proj" (absolute on Windows, relative on Linux) nor "/proj" (the reverse)
# works, and Path(os.sep) / "proj" gives "\\proj" on Windows, which is
# drive-relative. os.path.abspath of a drive-relative string is the one form
# that resolves to something both platforms call absolute.
_ROOT = Path(os.path.abspath(os.path.join(os.sep, "proj")))


def _p(*parts: str) -> str:
    """An absolute path on whichever host is running the tests."""
    return str(_ROOT.joinpath(*parts))


def _base(node_id: str) -> str:
    """The file name from a node id, whichever separator it carries."""
    return node_id.replace(chr(92), "/").rsplit("/", 1)[-1]


def _mk(fp: str, deps: list[IRDependency], language: str = "python") -> IRFileParseResult:
    return IRFileParseResult(
        file_path=fp,
        language=language,
        file_node=IRFileNode(
            id=f"file:{fp}",
            type=NodeType.FILE,
            name=fp.replace("\\", "/").rsplit("/", 1)[-1],
            source="test",
            file_path=fp,
            language=language,
            role=FileRole.UNKNOWN,
        ),
        dependencies=tuple(deps),
    )


def test_python_relative_same_dir():
    src = _mk(_p("pkg", "sub", "mod.py"), [
        IRDependency(source_file=_p("pkg", "sub", "mod.py"), target_module=".helpers", kind="importfrom", line=1),
    ])
    helper = _mk(_p("pkg", "sub", "helpers.py"), [])
    _, edges = resolve_imports_into_edges([src, helper])
    assert [(e.from_node, e.to_node) for e in edges] == [
        (_p("pkg", "sub", "mod.py"), _p("pkg", "sub", "helpers.py")),
    ]


def test_python_relative_parent_dir_via_dots_and_level():
    src_deps = [
        IRDependency(source_file=_p("pkg", "sub", "mod.py"), target_module="..up", kind="importfrom", line=1),
        IRDependency(source_file=_p("pkg", "sub", "mod.py"), target_module="sibling", kind="importfrom", line=2, level=1),
    ]
    src = _mk(_p("pkg", "sub", "mod.py"), src_deps)
    up = _mk(_p("pkg", "up.py"), [])
    sibling = _mk(_p("pkg", "sub", "sibling.py"), [])
    _, edges = resolve_imports_into_edges([src, up, sibling])
    pairs = sorted((_base(e.to_node), e.metadata["line"]) for e in edges)
    assert pairs == [("sibling.py", 2), ("up.py", 1)]
    assert all(e.from_node == _p("pkg", "sub", "mod.py") for e in edges)


def test_python_relative_package_init():
    src = _mk(_p("app", "main.py"), [
        IRDependency(source_file=_p("app", "main.py"), target_module=".subpkg", kind="importfrom", line=1),
    ])
    init = _mk(_p("app", "subpkg", "__init__.py"), [])
    _, edges = resolve_imports_into_edges([src, init])
    assert len(edges) == 1
    assert edges[0].to_node == _p("app", "subpkg", "__init__.py")


def test_single_dir_repo_intra_package_import_yields_edge():
    main = _mk("F:/repo/db/main.py", [
        IRDependency(source_file="F:/repo/db/main.py", target_module="db.helpers", kind="import", line=1),
    ])
    helper = _mk("F:/repo/db/helpers.py", [])
    initf = _mk("F:/repo/db/__init__.py", [])
    _, edges = resolve_imports_into_edges([main, helper, initf])
    assert len(edges) == 1
    assert edges[0].from_node == "F:/repo/db/main.py"
    assert edges[0].to_node == "F:/repo/db/helpers.py"


def test_single_dir_repo_flat_stem_import_still_resolves():
    main = _mk("F:/repo/db/main.py", [
        IRDependency(source_file="F:/repo/db/main.py", target_module="helpers", kind="import", line=1),
    ])
    helper = _mk("F:/repo/db/helpers.py", [])
    _, edges = resolve_imports_into_edges([main, helper])
    assert len(edges) == 1
    assert edges[0].to_node == "F:/repo/db/helpers.py"


def test_js_relative_import_extensions():
    app = _mk(_p("src", "app.ts"), [
        IRDependency(source_file=_p("src", "app.ts"), target_module="./utils", kind="import", line=1),
        IRDependency(source_file=_p("src", "app.ts"), target_module="../lib/mod.js", kind="import", line=2),
    ], language="typescript")
    utils = _mk(_p("src", "utils.ts"), [], language="typescript")
    mod = _mk(_p("lib", "mod.js"), [], language="javascript")
    _, edges = resolve_imports_into_edges([app, utils, mod])
    pairs = sorted((_base(e.from_node), e.to_node) for e in edges)
    assert pairs == [
        ("app.ts", _p("lib", "mod.js")),
        ("app.ts", _p("src", "utils.ts")),
    ]


def test_js_relative_index_resolution():
    page = _mk(_p("src", "page.js"), [
        IRDependency(source_file=_p("src", "page.js"), target_module="./components/button", kind="import", line=1),
    ], language="javascript")
    button = _mk(_p("src", "components", "button", "index.tsx"), [], language="javascript")
    _, edges = resolve_imports_into_edges([page, button])
    assert len(edges) == 1
    assert edges[0].to_node == _p("src", "components", "button", "index.tsx")


def test_perf_full_resolve_under_1s():
    root = Path(__file__).resolve().parents[1]
    py_files = [
        p for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and ".venv" not in p.parts
    ]
    results = []
    for p in py_files:
        fp = p.as_posix()
        deps = [
            IRDependency(source_file=fp, target_module="os", kind="import", line=1),
            IRDependency(source_file=fp, target_module="collections.defaultdict", kind="importfrom", line=2),
        ]
        results.append(_mk(fp, deps))
    t0 = time.perf_counter()
    resolve_imports_into_edges(results)
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"resolve took {elapsed:.3f}s for {len(results)} files"
