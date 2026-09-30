"""A registered repository must be findable however its path is spelled.

CI was red on all four runners with "Repository not registered" for a
repository that had just been registered. register_repo resolved the path to
a key, and index_repo looked the caller's raw string up in the same dict — so
any different spelling missed. The Windows runners spell temp directories
8.3-short ("C:\\Users\\RUNNER~1\\..."), which is exactly such a spelling.
"""

import logging
import os

import pytest

from astra.runtime.orchestrator import RuntimeOrchestrator


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return tmp_path


def _register(orchestrator, path):
    orchestrator.register_repo(str(path))
    return orchestrator


def test_lookup_by_a_relative_path_finds_the_same_record(repo, monkeypatch):
    logging.disable(logging.CRITICAL)
    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(repo))

    monkeypatch.chdir(repo.parent)
    record = orchestrator.get_repo(f"./{repo.name}")
    assert record is not None, "a relative spelling missed the registry"
    assert record.root_path == str(repo.resolve())


def test_lookup_by_a_trailing_separator_finds_the_same_record(repo):
    logging.disable(logging.CRITICAL)
    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(repo))
    assert orchestrator.get_repo(str(repo) + os.sep) is not None


def test_index_accepts_a_different_spelling(repo, monkeypatch):
    """The failure CI hit: register one way, index another."""
    logging.disable(logging.CRITICAL)
    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(repo))

    monkeypatch.chdir(repo.parent)
    record = orchestrator.index_repo(f"./{repo.name}")
    assert record.status.value == "active", record.error


def test_every_accessor_agrees_on_one_spelling(repo, monkeypatch):
    logging.disable(logging.CRITICAL)
    orchestrator = RuntimeOrchestrator()
    orchestrator.register_repo(str(repo))
    orchestrator.index_repo(str(repo))

    monkeypatch.chdir(repo.parent)
    alternate = f"./{repo.name}"
    assert orchestrator.get_repo(alternate) is not None
    assert orchestrator._get_record(alternate).root_path == str(repo.resolve())
    assert orchestrator._get_active_record(alternate).status.value == "active"
    assert orchestrator.remove_repo(alternate) is True


def test_registering_twice_returns_the_same_record(repo):
    logging.disable(logging.CRITICAL)
    orchestrator = RuntimeOrchestrator()
    first = orchestrator.register_repo(str(repo))
    second = orchestrator.register_repo(str(repo))
    assert first is second


def test_an_unregistered_path_is_still_rejected():
    logging.disable(logging.CRITICAL)
    orchestrator = RuntimeOrchestrator()
    with pytest.raises(ValueError, match="not registered"):
        orchestrator.index_repo("C:/definitely/not/a/repository")
