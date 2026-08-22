from types import SimpleNamespace

from astra.legacy.adapters import to_legacy_project_index
from astra.ir.models import IRFileNode, NodeType


def test_legacy_project_adapter_preserves_metadata():
    file_node = IRFileNode(
        id="file:test.py",
        type=NodeType.FILE,
        name="test.py",
        source="scanner",
        file_path="test.py",
    )

    repo_index = SimpleNamespace(
        files=[file_node],
        metadata={"scan": "ok"},
        language_summary={"python": 1},
        failures=[],
    )

    legacy = to_legacy_project_index(repo_index)

    assert len(legacy.files) == 1
    assert legacy.metadata["repository_scan"] == {"scan": "ok"}
    assert legacy.metadata["language_summary"] == {"python": 1}
