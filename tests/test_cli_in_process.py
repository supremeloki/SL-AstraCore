"""The CLI's own logic, exercised in this process.

test_cli.py runs the command in a subprocess, which is the only way to see
what a user sees — but that also means coverage tooling cannot see inside it,
and astra/cli/__init__.py measured 0%. These call main() directly, which is
where the branching actually lives.
"""


import pytest

import astra.cli as cli


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "billing.py").write_text(
        '"""Charging."""\n\n\ndef charge(amount):\n    return amount\n', encoding="utf-8"
    )
    return tmp_path


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for command in ("index", "context", "serve"):
        assert command in out, f"{command} is not offered"


def test_index_reports_the_graph(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRA_HOME", str(tmp_path / "home"))
    assert cli.main(["index", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "status=active" in out
    assert "nodes=" in out


def test_index_of_a_missing_path_fails(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRA_HOME", str(tmp_path / "home"))
    assert cli.main(["index", str(repo / "nope")]) == 1
    assert "error:" in capsys.readouterr().err


def test_context_prints_the_pack(repo, capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRA_HOME", str(tmp_path / "home"))
    assert cli.main(["index", str(repo)]) == 0
    capsys.readouterr()
    assert cli.main(["context", str(repo), "how does charging work"]) == 0
    out = capsys.readouterr().out
    assert "billing.py" in out
    assert "tokens~" in out


def test_context_indexes_when_the_repo_was_never_indexed(repo, capsys, tmp_path, monkeypatch):
    """The path a user actually takes: query a repo they only just pointed at."""
    monkeypatch.setenv("ASTRA_HOME", str(tmp_path / "home"))
    assert cli.main(["context", str(repo), "charge"]) == 0
    assert "billing.py" in capsys.readouterr().out


def test_context_reports_more_nodes_than_it_prints(repo, capsys, tmp_path, monkeypatch):
    """The '... N more' line, which only a pack over 20 nodes reaches."""
    for index in range(30):
        (repo / f"module{index}.py").write_text(
            f"def handler_{index}():\n    return {index}\n", encoding="utf-8"
        )
    monkeypatch.setenv("ASTRA_HOME", str(tmp_path / "home"))
    assert cli.main(["context", str(repo), "handler"]) == 0
    assert "more" in capsys.readouterr().out


def test_serve_starts_uvicorn(repo, monkeypatch):
    started = {}

    def fake_run(target, host, port):
        started.update(target=target, host=host, port=port)

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    assert cli.main(["serve", "--port", "9123"]) == 0
    assert started == {"target": "dashboard_app:app", "host": "127.0.0.1", "port": 9123}


def test_serve_defaults_to_port_8000(monkeypatch):
    ports = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: ports.append(k["port"]))
    cli.main(["serve"])
    assert ports == [8000]


def test_console_main_raises_system_exit_with_the_code(monkeypatch):
    """Why console_main exists: setuptools discards a plain return value."""
    monkeypatch.setattr(cli, "main", lambda: 1)
    with pytest.raises(SystemExit) as exit_info:
        cli.console_main()
    assert exit_info.value.code == 1


def test_a_path_with_a_trailing_separator_is_the_same_repo(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRA_HOME", str(tmp_path / "home"))
    import os

    assert cli.main(["index", str(repo) + os.sep]) == 0


def test_query_requires_both_arguments(repo):
    with pytest.raises(SystemExit):
        cli.main(["context", str(repo)])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
