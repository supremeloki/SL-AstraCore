from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from astra.ir.models import (
    ArchitectureLayer,
    FileRole,
    IRFileNode,
    IRProjectIndex,
    RiskLevel,
    Stability,
    NodeType,
)
from astra.scanner.repository_scanner import RepositoryScanner


@dataclass(frozen=True)
class ScannerIntegrationResult:
    project_index: IRProjectIndex
    files: tuple[IRFileNode, ...]


class RepositoryScannerIntegrator:
    """Bridges legacy RepositoryScanner output into Canonical IR.

    Scanner ownership stays isolated here.
    """

    def __init__(self, root_path: str) -> None:
        self._root_path = str(Path(root_path).resolve())
        self._scanner = RepositoryScanner(self._root_path)

    def scan_to_ir(self) -> ScannerIntegrationResult:
        scanned = self._scanner.scan()

        files: list[IRFileNode] = []
        languages: dict[str, int] = {}
        total_lines = 0
        total_bytes = 0

        for item in scanned:
            language = getattr(item, "language", "unknown") or "unknown"
            rel_path = getattr(item, "rel_path", getattr(item, "path", ""))
            abs_path = str(Path(self._root_path) / rel_path)
            size = int(getattr(item, "size_bytes", 0) or 0)

            line_count = int(getattr(item, "line_count", 0) or 0)

            node = IRFileNode(
                id=f"file:{abs_path}",
                type=NodeType.FILE,
                name=Path(abs_path).name,
                source="scanner",
                confidence=0.95,
                file_path=abs_path,
                language=language,
                role=FileRole.UNKNOWN,
                line_count=line_count,
                byte_size=size,
                is_binary=bool(getattr(item, "is_binary", False)),
                is_vault=abs_path.endswith((".md", ".markdown")),
                architecture_layer=ArchitectureLayer.UNKNOWN,
                stability=Stability.STABLE,
                risk_level=RiskLevel.LOW,
            )

            files.append(node)
            languages[language] = languages.get(language, 0) + 1
            total_lines += line_count
            total_bytes += size

        project = IRProjectIndex(
            project_root=self._root_path,
            file_count=len(files),
            total_lines=total_lines,
            total_bytes=total_bytes,
            languages=languages,
            vault_note_count=sum(1 for f in files if f.is_vault),
            binary_count=sum(1 for f in files if f.is_binary),
            files=tuple(files),
        )

        return ScannerIntegrationResult(
            project_index=project,
            files=tuple(files),
        )