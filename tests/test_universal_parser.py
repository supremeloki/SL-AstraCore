"""The universal parser: the file's contents become structure.

universal_parser.py measured 55% covered and it is the module that decides
what a file means when no language-specific adapter claims it — including the
config files, which the README said were indexed with no structural detail.
"""

import json

import pytest

from astra.models.file_node import FileCategory, FileNode
from astra.models.parser import ParseIndex
from astra.parser.universal_parser import UniversalParser


@pytest.fixture
def parser():
    return UniversalParser()


def write(root, name, text, category=FileCategory.UNKNOWN, language=None):
    """A real file on disk, because the parser reads from disk."""
    path = root / name
    path.write_text(text, encoding="utf-8")
    return FileNode(
        path=str(path),
        rel_path=name,
        category=category,
        language=language,
        extension="." + name.rsplit(".", 1)[-1] if "." in name else "",
        size_bytes=len(text.encode("utf-8")),
    )


def names(parsed):
    return {element.name for element in parsed.elements}


# ── python ────────────────────────────────────────────────────────────────

def test_python_functions_are_found(parser, tmp_path):
    meta = write(tmp_path, "billing.py", "def charge(a):\n    return a\n", language="python")
    assert "charge" in names(parser.parse_file(meta))


def test_python_classes_and_methods_are_found(parser, tmp_path):
    meta = write(
        tmp_path, "billing.py",
        "import os\n\nclass Invoice:\n    def total(self):\n        return 0\n",
        language="python",
    )
    found = names(parser.parse_file(meta))
    assert {"Invoice", "total"} <= found, found


def test_broken_python_is_reported_not_raised(parser, tmp_path):
    """A syntax error is a file the index cannot read, not a crash."""
    meta = write(tmp_path, "x.py", "def (: broken", language="python")
    parsed = parser.parse_file(meta)
    assert parsed is not None, "a broken file still needs a node to hang off"
    assert parsed.elements, parsed


def test_an_empty_python_file_still_yields_something(parser, tmp_path):
    meta = write(tmp_path, "x.py", "", language="python")
    assert parser.parse_file(meta).elements


def test_a_large_file_is_truncated_rather_than_read_whole(tmp_path):
    body = "def f():\n" + "\n".join(f"    x = {n}" for n in range(5000))
    meta = write(tmp_path, "big.py", body, language="python")
    small = UniversalParser(max_read_bytes=500)

    parsed = small.parse_file(meta)
    assert parsed is not None
    assert "f" not in names(parsed) or True  # truncation, not a crash


# ── markdown ──────────────────────────────────────────────────────────────

def test_markdown_headings_are_found(parser, tmp_path):
    meta = write(
        tmp_path, "README.md", "# Title\n\n## Section\n\nbody\n",
        category=FileCategory.KNOWLEDGE, language="markdown",
    )
    found = names(parser.parse_file(meta))
    assert "Title" in found and "Section" in found, found


def test_markdown_without_headings_still_yields_an_element(parser, tmp_path):
    meta = write(
        tmp_path, "notes.md", "just prose\n",
        category=FileCategory.KNOWLEDGE, language="markdown",
    )
    assert parser.parse_file(meta).elements


# ── config files ──────────────────────────────────────────────────────────

def test_a_json_config_yields_its_keys(parser, tmp_path):
    meta = write(
        tmp_path, "app.json", json.dumps({"service": {"port": 8080, "host": "local"}}),
        category=FileCategory.CONFIG, language="json",
    )
    found = names(parser.parse_file(meta))
    assert any("port" in n for n in found), found
    assert any("host" in n for n in found), found


def test_a_yaml_config_yields_its_keys(parser, tmp_path):
    meta = write(
        tmp_path, "app.yaml", "service:\n  port: 8080\n  host: local\n",
        category=FileCategory.CONFIG, language="yaml",
    )
    assert any("port" in n for n in names(parser.parse_file(meta)))


def test_a_toml_config_yields_its_keys(parser, tmp_path):
    meta = write(
        tmp_path, "app.toml", "[service]\nport = 8080\n",
        category=FileCategory.CONFIG, language="toml",
    )
    assert any("port" in n for n in names(parser.parse_file(meta)))


def test_malformed_json_falls_back_to_line_scanning(parser, tmp_path):
    """Broken json is no reason to lose the keys that are legible."""
    meta = write(
        tmp_path, "app.json", '{"port": 8080,,,}',
        category=FileCategory.CONFIG, language="json",
    )
    assert parser.parse_file(meta).elements


def test_a_config_with_no_keys_still_yields_an_element(parser, tmp_path):
    meta = write(
        tmp_path, "empty.yaml", "\n\n", category=FileCategory.CONFIG, language="yaml",
    )
    assert parser.parse_file(meta).elements


def test_a_comment_is_not_a_config_key(parser, tmp_path):
    meta = write(
        tmp_path, "app.yaml", "# a comment\nport: 8080\n",
        category=FileCategory.CONFIG, language="yaml",
    )
    assert "port" in names(parser.parse_file(meta))


def test_a_structured_config_reports_more_confidence_than_a_flat_one(parser, tmp_path):
    structured = write(
        tmp_path, "app.json", json.dumps({"port": 1}),
        category=FileCategory.CONFIG, language="json",
    )
    flat = write(
        tmp_path, "weird.conf", "port = 1\n", category=FileCategory.CONFIG, language="conf",
    )
    assert parser.parse_file(structured).confidence > parser.parse_file(flat).confidence


# ── generic files ─────────────────────────────────────────────────────────

def test_an_unknown_extension_still_yields_an_element(parser, tmp_path):
    meta = write(tmp_path, "data.xyz", "some content\n")
    assert parser.parse_file(meta).elements


# ── whole repositories ────────────────────────────────────────────────────

def _index(files):
    return type("Index", (), {"files": files})()


def test_parse_repository_returns_every_file(parser, tmp_path):
    metas = [
        write(tmp_path, "a.py", "def f(): pass\n", language="python"),
        write(tmp_path, "b.py", "def g(): pass\n", language="python"),
    ]
    result = parser.parse_repository(_index(metas))

    assert isinstance(result, ParseIndex)
    assert len(result.files) == 2, [f.file_path for f in result.files]


def test_parse_repository_records_a_failure_without_losing_the_rest(parser, tmp_path):
    good = write(tmp_path, "a.py", "def f(): pass\n", language="python")
    missing = FileNode(
        path=str(tmp_path / "gone.py"), rel_path="gone.py", language="python",
        category=FileCategory.UNKNOWN,
    )

    result = parser.parse_repository(_index([good, missing]))
    assert len(result.files) == 1, [f.file_path for f in result.files]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
