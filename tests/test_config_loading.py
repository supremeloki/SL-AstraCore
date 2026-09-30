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


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
