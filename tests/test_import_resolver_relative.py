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


def _mk(fp: str, deps: list[IRDependency], language: str = "python") -> IRFileParseResult:
    return IRFileParseResult(
        file_path=fp,
        language=language,
        file_node=IRFileNode(
            id=f"file:{fp}",
            type=NodeType.FILE,
            name=fp.split("/")[-1],
            source="test",
            file_path=fp,
            language=language,
            role=FileRole.UNKNOWN,
        ),
        dependencies=tuple(deps),
    )


def test_python_relative_same_dir():
    src = _mk("F:/proj/pkg/sub/mod.py", [
        IRDependency(source_file="F:/proj/pkg/sub/mod.py", target_module=".helpers", kind="importfrom", line=1),
    ])
    helper = _mk("F:/proj/pkg/sub/helpers.py", [])
    _, edges = resolve_imports_into_edges([src, helper])
    assert [(e.from_node, e.to_node) for e in edges] == [
        ("F:/proj/pkg/sub/mod.py", "F:/proj/pkg/sub/helpers.py"),
    ]


def test_python_relative_parent_dir_via_dots_and_level():
    src_deps = [
        IRDependency(source_file="F:/proj/pkg/sub/mod.py", target_module="..up", kind="importfrom", line=1),
        IRDependency(source_file="F:/proj/pkg/sub/mod.py", target_module="sibling", kind="importfrom", line=2, level=1),
    ]
    src = _mk("F:/proj/pkg/sub/mod.py", src_deps)
    up = _mk("F:/proj/pkg/up.py", [])
    sibling = _mk("F:/proj/pkg/sub/sibling.py", [])
    _, edges = resolve_imports_into_edges([src, up, sibling])
    pairs = sorted((e.to_node.split("/")[-1], e.metadata["line"]) for e in edges)
    assert pairs == [("sibling.py", 2), ("up.py", 1)]
    assert all(e.from_node == "F:/proj/pkg/sub/mod.py" for e in edges)


def test_python_relative_package_init():
    src = _mk("F:/proj/app/main.py", [
        IRDependency(source_file="F:/proj/app/main.py", target_module=".subpkg", kind="importfrom", line=1),
    ])
    init = _mk("F:/proj/app/subpkg/__init__.py", [])
    _, edges = resolve_imports_into_edges([src, init])
    assert len(edges) == 1
    assert edges[0].to_node == "F:/proj/app/subpkg/__init__.py"


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
    app = _mk("F:/proj/src/app.ts", [
        IRDependency(source_file="F:/proj/src/app.ts", target_module="./utils", kind="import", line=1),
        IRDependency(source_file="F:/proj/src/app.ts", target_module="../lib/mod.js", kind="import", line=2),
    ], language="typescript")
    utils = _mk("F:/proj/src/utils.ts", [], language="typescript")
    mod = _mk("F:/proj/lib/mod.js", [], language="javascript")
    _, edges = resolve_imports_into_edges([app, utils, mod])
    pairs = sorted((e.from_node.split("/")[-1], e.to_node) for e in edges)
    assert pairs == [
        ("app.ts", "F:/proj/lib/mod.js"),
        ("app.ts", "F:/proj/src/utils.ts"),
    ]


def test_js_relative_index_resolution():
    page = _mk("F:/proj/src/page.js", [
        IRDependency(source_file="F:/proj/src/page.js", target_module="./components/button", kind="import", line=1),
    ], language="javascript")
    button = _mk("F:/proj/src/components/button/index.tsx", [], language="javascript")
    _, edges = resolve_imports_into_edges([page, button])
    assert len(edges) == 1
    assert edges[0].to_node == "F:/proj/src/components/button/index.tsx"


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
