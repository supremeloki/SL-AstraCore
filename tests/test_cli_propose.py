"""`astra propose` — review an edit without writing it."""

import json

import pytest

import astra.cli as cli


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "billing.py").write_text(
        "def charge(amount):\n    return amount - 1\n", encoding="utf-8"
    )
    monkeypatch.setenv("ASTRA_HOME", str(tmp_path / "home"))
    return tmp_path


def _reply(old="return amount - 1", new="return amount"):
    return json.dumps({"edits": [{
        "path": "billing.py", "old_text": old, "new_text": new, "reason": "off by one",
    }]})


def test_a_well_formed_reply_is_reviewed(repo, capsys):
    assert cli.main(["propose", str(repo), "fix the charge", "--reply", _reply()]) == 0
    out = capsys.readouterr().out
    assert "risk:" in out
    assert "billing.py" in out


def test_proposing_writes_nothing(repo, capsys):
    before = (repo / "billing.py").read_text(encoding="utf-8")
    cli.main(["propose", str(repo), "fix it", "--reply", _reply()])
    assert (repo / "billing.py").read_text(encoding="utf-8") == before


def test_it_says_nothing_was_written(repo, capsys):
    cli.main(["propose", str(repo), "fix it", "--reply", _reply()])
    assert "nothing was written" in capsys.readouterr().out


def test_a_reply_from_a_file_is_accepted(repo, tmp_path, capsys):
    reply_file = tmp_path / "proposal.json"
    reply_file.write_text(_reply(), encoding="utf-8")
    assert cli.main([
        "propose", str(repo), "fix it", "--reply", str(reply_file)
    ]) == 0
    assert "risk:" in capsys.readouterr().out


def test_a_reply_from_stdin_is_accepted(repo, capsys, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(_reply()))
    assert cli.main(["propose", str(repo), "fix it", "--reply", "-"]) == 0
    assert "billing.py" in capsys.readouterr().out


def test_an_unusable_reply_fails(repo, capsys):
    assert cli.main([
        "propose", str(repo), "fix it", "--reply", "I cannot help"
    ]) == 1
    assert "could not be used" in capsys.readouterr().err


def test_an_unanchored_edit_fails(repo, capsys):
    assert cli.main([
        "propose", str(repo), "fix it",
        "--reply", _reply(old="def never_existed(): ..."),
    ]) == 1
    assert "rejected" in capsys.readouterr().err


def test_propose_appears_in_help(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "propose" in capsys.readouterr().out
