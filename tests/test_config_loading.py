"""astra/core had no test coverage at all.

Config is reachable from the project settings file, so the parser and the
coercion rules are worth pinning even though the current production entry
points construct it only through the (dead) AstraCore wrapper.
"""

import logging

from astra.core.config import Config


def test_defaults_apply_when_no_file_exists(tmp_path):
    logging.disable(logging.CRITICAL)
    config = Config(tmp_path)
    assert config.get("storage.engine") == "duckdb"
    assert config.get("scanner.follow_symlinks") is False
    # An unknown key must not raise; it falls back to the caller's default.
    assert config.get("nope.missing", "fallback") == "fallback"
    assert config.get("nope.missing") is None


def test_nested_yaml_overrides_only_the_keys_it_names(tmp_path):
    logging.disable(logging.CRITICAL)
    (tmp_path / "astra.yaml").write_text(
        "scanner:\n"
        "  follow_symlinks: true\n"
        "  max_file_size_kb: 2048\n",
        encoding="utf-8",
    )
    config = Config(tmp_path)
    assert config.get("scanner.follow_symlinks") is True
    assert config.get("scanner.max_file_size_kb") == 2048
    # A sibling key not mentioned in the file keeps its default.
    assert config.get("scanner.hash_algorithm") == "sha256"


def test_comments_and_blank_lines_are_ignored(tmp_path):
    logging.disable(logging.CRITICAL)
    (tmp_path / "astra.yaml").write_text(
        "# leading comment\n\nscanner:\n  # nested comment\n  worker_count: 4\n",
        encoding="utf-8",
    )
    config = Config(tmp_path)
    assert config.get("scanner.worker_count") == 4


def test_values_are_coerced_to_their_yaml_types(tmp_path):
    logging.disable(logging.CRITICAL)
    (tmp_path / "astra.yaml").write_text(
        "scanner:\n"
        "  worker_count: 7\n"
        "  follow_symlinks: true\n"
        "  hash_algorithm: sha512\n",
        encoding="utf-8",
    )
    config = Config(tmp_path)
    assert config.get("scanner.worker_count") == 7
    assert isinstance(config.get("scanner.worker_count"), int)
    assert config.get("scanner.follow_symlinks") is True
    assert config.get("scanner.hash_algorithm") == "sha512"
    assert isinstance(config.get("scanner.hash_algorithm"), str)


def test_dotted_keys_report_a_missing_path_instead_of_raising(tmp_path):
    logging.disable(logging.CRITICAL)
    (tmp_path / "astra.yaml").write_text("scanner:\n  worker_count: 2\n", encoding="utf-8")
    config = Config(tmp_path)
    # Asking for a leaf under a key that has no children is a miss, not a crash.
    assert config.get("scanner.worker_count.deeper") is None
    assert config.get("scanner.worker_count.deeper", 1) == 1


def test_raw_exposes_the_file_as_parsed(tmp_path):
    logging.disable(logging.CRITICAL)
    (tmp_path / "astra.yaml").write_text(
        "scanner:\n  worker_count: 3\n", encoding="utf-8"
    )
    config = Config(tmp_path)

    assert config.raw == {"scanner": {"worker_count": 3}}
    config.raw["scanner"]["worker_count"] = 99
    assert config.get("scanner.worker_count") == 3, "raw handed out the live tree"


def test_raw_is_empty_without_a_file(tmp_path):
    logging.disable(logging.CRITICAL)
    assert Config(tmp_path).raw == {}


def test_project_path_is_the_directory_it_was_given(tmp_path):
    logging.disable(logging.CRITICAL)
    assert Config(tmp_path).project_path == tmp_path


def test_a_malformed_file_does_not_crash(tmp_path):
    logging.disable(logging.CRITICAL)
    (tmp_path / "astra.yaml").write_text(
        "\x00 not yaml at all: [", encoding="utf-8"
    )
    # Whatever it yields, get() must answer rather than raise.
    config = Config(tmp_path)
    assert config.get("storage.engine", "duckdb") is not None


def test_an_unreadable_file_falls_back_to_the_defaults(tmp_path, monkeypatch):
    """A settings file locked by another process must not disable the tool."""
    import builtins

    logging.disable(logging.CRITICAL)
    (tmp_path / "astra.yaml").write_text("storage:\n  engine: sqlite\n", encoding="utf-8")

    real_open = builtins.open

    def refuse(path, *args, **kwargs):
        if str(path).endswith("astra.yaml"):
            raise PermissionError(32, "locked by another process")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", refuse)
    config = Config(tmp_path)

    assert config.get("storage.engine") == "duckdb", (
        "an unreadable settings file should leave the defaults in place"
    )


# ── the parser used when pyyaml is absent ─────────────────────────────────
# astra/core/config.py imports yaml in a try block and falls back to a
# hand-written parser. Nothing exercised the fallback, which is the one a
# minimal install runs.

def _without_pyyaml(monkeypatch):
    import astra.core.config as module

    monkeypatch.setattr(module, "yaml", None)


def test_the_fallback_parser_reads_nesting_and_scalars(tmp_path, monkeypatch):
    logging.disable(logging.CRITICAL)
    _without_pyyaml(monkeypatch)
    (tmp_path / "astra.yaml").write_text(
        "scanner:\n"
        "  worker_count: 7\n"
        "  follow_symlinks: true\n"
        "  checkpoint_path: '/tmp/ck'\n"
        "storage:\n"
        "  engine: sqlite\n",
        encoding="utf-8",
    )
    config = Config(tmp_path)

    assert config.get("scanner.worker_count") == 7
    assert config.get("scanner.follow_symlinks") is True
    assert config.get("scanner.checkpoint_path") == "/tmp/ck"
    assert config.get("storage.engine") == "sqlite"


def test_the_fallback_parser_ignores_comments_and_blanks(tmp_path, monkeypatch):
    logging.disable(logging.CRITICAL)
    _without_pyyaml(monkeypatch)
    (tmp_path / "astra.yaml").write_text(
        "# a comment\n\nscanner:\n  # nested\n  worker_count: 2\n",
        encoding="utf-8",
    )
    assert Config(tmp_path).get("scanner.worker_count") == 2


def test_the_fallback_parser_mangles_yaml_lists(tmp_path, monkeypatch):
    """A known gap, pinned so it cannot regress silently.

    A list item is a line starting with "- ", which _simple_yaml skips, so
    `providers:` becomes an empty mapping rather than a list. pyyaml is a hard
    dependency in pyproject.toml, so this path only runs on a partial
    install — but it runs silently wrong rather than loudly, which is worse.
    """
    logging.disable(logging.CRITICAL)
    _without_pyyaml(monkeypatch)
    (tmp_path / "astra.yaml").write_text(
        "agent:\n  providers:\n    - generic\n    - codex\n", encoding="utf-8"
    )
    config = Config(tmp_path)

    assert config.raw["agent"]["providers"] == {}, (
        "the fallback parser turned a YAML list into an empty mapping"
    )
    assert config.get("agent.providers") == {}, (
        "and get() reports that empty mapping as the value"
    )


def test_an_inline_yaml_list_stays_a_string(tmp_path, monkeypatch):
    logging.disable(logging.CRITICAL)
    _without_pyyaml(monkeypatch)
    (tmp_path / "astra.yaml").write_text(
        "agent:\n  providers: [generic, codex]\n", encoding="utf-8"
    )
    assert Config(tmp_path).get("agent.providers") == "[generic, codex]"


def test_the_fallback_parser_coerces_scalars(tmp_path, monkeypatch):
    logging.disable(logging.CRITICAL)
    _without_pyyaml(monkeypatch)
    (tmp_path / "astra.yaml").write_text(
        "scanner:\n  n: 12\n  yes: true\n  no: false\n  word: hello\n",
        encoding="utf-8",
    )
    config = Config(tmp_path)

    assert config.get("scanner.n") == 12 and isinstance(config.get("scanner.n"), int)
    assert config.get("scanner.yes") is True
    assert config.get("scanner.no") is False
    assert config.get("scanner.word") == "hello"


def test_both_parsers_agree_on_the_same_file(tmp_path, monkeypatch):
    """The fallback has to mean the same thing as pyyaml, or it is a trap."""
    import astra.core.config as module

    text = (
        "scanner:\n"
        "  worker_count: 7\n"
        "  follow_symlinks: true\n"
        "storage:\n"
        "  engine: sqlite\n"
    )
    (tmp_path / "astra.yaml").write_text(text, encoding="utf-8")

    if module.yaml is None:
        pytest.skip("pyyaml is not installed, so there is nothing to compare against")

    with_yaml = {k: Config(tmp_path).get(k) for k in
                 ("scanner.worker_count", "scanner.follow_symlinks", "storage.engine")}

    monkeypatch.setattr(module, "yaml", None)
    without_yaml = {k: Config(tmp_path).get(k) for k in
                    ("scanner.worker_count", "scanner.follow_symlinks", "storage.engine")}

    assert with_yaml == without_yaml, (with_yaml, without_yaml)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
