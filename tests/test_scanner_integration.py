from __future__ import annotations

import tempfile
from pathlib import Path

from astra.scanner.integration import RepositoryScannerIntegrator


PY_FILE = '''
def hello():
    return "world"
'''

MD_FILE = '''
# Architecture
'''


def test_scanner_integration_to_ir():
    with tempfile.TemporaryDirectory(prefix="astra_scan_") as tmpdir:
        root = Path(tmpdir)

        (root / "app.py").write_text(PY_FILE)
        (root / "notes.md").write_text(MD_FILE)

        integrator = RepositoryScannerIntegrator(str(root))
        result = integrator.scan_to_ir()

        project = result.project_index
        files = result.files

        assert project.file_count >= 2
        assert len(files) >= 2

        paths = {f.file_path for f in files}
        assert str(root / "app.py") in paths
        assert str(root / "notes.md") in paths

        langs = project.languages
        assert "python" in langs or "unknown" in langs

        md_nodes = [f for f in files if f.file_path.endswith("notes.md")]
        assert md_nodes
        assert md_nodes[0].is_vault is True

        py_nodes = [f for f in files if f.file_path.endswith("app.py")]
        assert py_nodes
        assert py_nodes[0].language in ("python", "unknown")