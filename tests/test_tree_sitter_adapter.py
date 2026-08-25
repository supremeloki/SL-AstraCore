from astra.parser.registry import build_default_parser_registry

import pytest

tree_sitter_pack = pytest.importorskip("tree_sitter_language_pack")

_CASES = [
    ("main.go", 'package main\nimport "fmt"\nfunc Run() { fmt.Println("x") }', ["Run"], []),
    ("lib.rs", "use std::io;\nfn run() {}\nstruct Config;", ["run"], ["Config"]),
    ("App.java", "package app;\nimport java.util.List;\nclass App { void go() {} }", ["go"], ["App"]),
    ("m.c", "#include <stdio.h>\nint main(void) { return 0; }", ["main"], []),
    ("m.cpp", "#include <vector>\nclass F {};\nint main() { return 0; }", ["main", "F"], []),
    ("Svc.cs", "using System.IO;\nclass Svc { void Run() {} }", ["Run"], ["Svc"]),
    ("tool.rb", 'require "json"\nclass Foo\n  def bar\n    1\n  end\nend', ["bar"], ["Foo"]),
    (
        "inc.php",
        "<?php namespace App;\nuse Foo\\Bar;\nclass Baz { public function qux() {} }",
        ["qux"],
        ["Baz"],
    ),
]


@pytest.mark.parametrize("path,source,want_fns,want_classes", _CASES)
def test_tree_sitter_symbols(path, source, want_fns, want_classes):
    registry = build_default_parser_registry()
    result = registry.parse(path, source)
    assert result is not None
    assert result.parse_errors == ()
    names = [s.name for s in result.symbols]
    for expected in want_fns + want_classes:
        assert expected in names


@pytest.mark.parametrize(
    "path,source,expected_dep",
    [
        ('main.go', 'import "fmt"', "fmt"),
        ("lib.rs", "use std::io;", "std::io;"),
        ("App.java", "import java.util.List;", "java.util.List;"),
        ("m.c", "#include <stdio.h>", "#include <stdio.h>"),
        ("Svc.cs", "using System.IO;", "using System.IO;"),
        ("tool.rb", 'require "json"', "json"),
    ],
)
def test_tree_sitter_dependencies(path, source, expected_dep):
    registry = build_default_parser_registry()
    result = registry.parse(path, source)
    targets = [d.target_module for d in result.dependencies]
    assert any(expected_dep in t for t in targets)


def test_registry_includes_tree_sitter_languages():
    langs = build_default_parser_registry().supported_languages()
    for lang in ("go", "rust", "java", "c", "cpp", "csharp", "ruby", "php"):
        assert lang in langs
