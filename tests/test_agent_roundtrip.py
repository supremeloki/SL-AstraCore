"""The whole loop: propose, then apply, then refuse a stale proposal.

The two halves are covered separately in test_agent_loop.py and
test_cli_propose.py. This is the path a user actually walks, and the property
worth guarding is that nothing is written until the second command.
"""

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


def a_reply(old="return amount - 1", new="return amount"):
    return json.dumps({"edits": [{
        "path": "billing.py", "old_text": old, "new_text": new, "reason": "off by one",
    }]})


def test_propose_then_apply_changes_the_file(repo, tmp_path, capsys):
    proposal = tmp_path / "proposal.json"

    assert cli.main([
        "propose", str(repo), "charge amount",
        "--reply", a_reply(), "--emit", str(proposal),
    ]) == 0

    # Between the two commands nothing has changed.
    assert (repo / "billing.py").read_text(encoding="utf-8") == (
        "def charge(amount):\n    return amount - 1\n"
    )
    assert proposal.exists(), "the proposal was not written"

    assert cli.main(["apply", str(repo), str(proposal)]) == 0
    assert "return amount" in (repo / "billing.py").read_text(encoding="utf-8")


def test_apply_refuses_a_proposal_the_file_has_outgrown(repo, tmp_path):
    proposal = tmp_path / "proposal.json"
    cli.main([
        "propose", str(repo), "charge amount",
        "--reply", a_reply(), "--emit", str(proposal),
    ])

    # Someone edits the file after the review but before the apply.
    (repo / "billing.py").write_text(
        "def charge(amount):\n    return amount - 99\n", encoding="utf-8"
    )

    assert cli.main(["apply", str(repo), str(proposal)]) == 1
    assert "amount - 99" in (repo / "billing.py").read_text(encoding="utf-8"), (
        "a stale proposal was applied anyway"
    )


def test_apply_refuses_an_unreviewed_proposal(repo, tmp_path):
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps({
        "clean": False,
        "warnings": ["the edit was not anchored"],
        "edits": [{
            "path": "billing.py",
            "old_text": "return amount - 1",
            "new_text": "return amount",
        }],
    }), encoding="utf-8")

    assert cli.main(["apply", str(repo), str(proposal)]) == 1
    assert "return amount - 1" in (repo / "billing.py").read_text(encoding="utf-8")


def test_apply_reports_an_unreadable_proposal(repo, tmp_path):
    assert cli.main(["apply", str(repo), str(tmp_path / "missing.json")]) == 1


def test_apply_of_an_empty_proposal_is_a_no_op(repo, tmp_path, capsys):
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps({"clean": True, "edits": []}), encoding="utf-8")

    assert cli.main(["apply", str(repo), str(proposal)]) == 0
    assert "no edits" in capsys.readouterr().out
    assert "return amount - 1" in (repo / "billing.py").read_text(encoding="utf-8")


def test_the_emitted_proposal_carries_the_fingerprints(repo, tmp_path):
    proposal = tmp_path / "proposal.json"
    cli.main([
        "propose", str(repo), "charge amount", "--reply", a_reply(), "--emit", str(proposal),
    ])
    payload = json.loads(proposal.read_text(encoding="utf-8"))

    assert payload["clean"] is True
    assert payload["fingerprints"], "the proposal must prove which file it reviewed"
    assert payload["edits"][0]["old_text"]
