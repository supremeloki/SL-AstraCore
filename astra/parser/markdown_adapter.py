from __future__ import annotations

import re
from pathlib import Path

from astra.ir.models import (
    FileRole,
    IRDependency,
    IRFileNode,
    IRFileParseResult,
    IRVaultConceptNode,
    NodeType,
    VaultConceptKind,
)

_HEADING_RE = re.compile(r"^#+\s+(.+)$", re.MULTILINE)
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


class MarkdownParserAdapter:
    language = "markdown"
    file_extensions = (".md", ".markdown")

    def can_parse(self, file_path: str) -> bool:
        return any(file_path.endswith(ext) for ext in self.file_extensions)

    def parse(self, file_path: str, content: str) -> IRFileParseResult:
        vault_concepts = []
        errors: list[str] = []

        try:
            for m in _HEADING_RE.finditer(content):
                heading = m.group(1).strip()
                vault_concepts.append(
                    IRVaultConceptNode(
                        id=f"vault:{file_path}:{heading}",
                        type=NodeType.VAULT_CONCEPT,
                        name=heading,
                        source="md-parser",
                        concept_type=VaultConceptKind.NOTE,
                        file_path=file_path,
                        confidence=0.7,
                    )
                )
        except Exception as e:
            errors.append(str(e))

        file_node = IRFileNode(
            id=f"file:{file_path}",
            type=NodeType.FILE,
            name=Path(file_path).name,
            source="md-parser",
            file_path=file_path,
            language="markdown",
            role=FileRole.UNKNOWN,
            line_count=content.count("\n") + 1,
            byte_size=len(content.encode("utf-8")),
            is_vault=True,
            confidence=0.8,
        )

        return IRFileParseResult(
            file_path=file_path,
            language="markdown",
            file_node=file_node,
            vault_concepts=tuple(vault_concepts),
            parse_errors=tuple(errors),
            confidence=0.8,
        )
