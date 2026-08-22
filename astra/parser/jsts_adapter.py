from __future__ import annotations

import re
from pathlib import Path

from astra.ir.models import (
    FileRole,
    IRClassNode,
    IRDependency,
    IRFileNode,
    IRFileParseResult,
    IRFunctionNode,
    IRSymbol,
    NodeType,
    SymbolKind,
)


_FUNCTION_RE = re.compile(
    r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(',
    re.MULTILINE,
)

_ARROW_RE = re.compile(
    r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>',
    re.MULTILINE,
)

_CLASS_RE = re.compile(
    r'(?:export\s+)?class\s+(\w+)',
    re.MULTILINE,
)

_IMPORT_RE = re.compile(
    r"""import\s+(?:
        (?:\{[^}]+\}|\w+|\*\s+as\s+\w+)\s+from\s+['"]([^'"]+)['"]  # named/default
        |
        \*\s+as\s+\w+\s+from\s+['"]([^'"]+)['"]                      # namespace
        |
        ['"]([^'"]+)['"]                                             # side-effect
    )""",
    re.MULTILINE | re.VERBOSE,
)


_CLASS_METHOD_RE = re.compile(
    r'^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*\S+)?\s*\{',
    re.MULTILINE,
)


class JSTSParserAdapter:
    language = "javascript"
    file_extensions = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")

    def can_parse(self, file_path: str) -> bool:
        return any(file_path.endswith(ext) for ext in self.file_extensions)

    def parse(self, file_path: str, content: str) -> IRFileParseResult:
        symbols: list[IRSymbol] = []

        for m in _FUNCTION_RE.finditer(content):
            symbols.append(IRSymbol(
                name=m.group(1),
                kind=SymbolKind.FUNCTION,
                file_path=file_path,
                line_start=content[:m.start()].count("\n") + 1,
                line_end=content[:m.start()].count("\n") + 1,
            ))

        for m in _ARROW_RE.finditer(content):
            symbols.append(IRSymbol(
                name=m.group(1),
                kind=SymbolKind.FUNCTION,
                file_path=file_path,
                line_start=content[:m.start()].count("\n") + 1,
                line_end=content[:m.start()].count("\n") + 1,
            ))

        for m in _CLASS_RE.finditer(content):
            symbols.append(IRSymbol(
                name=m.group(1),
                kind=SymbolKind.CLASS,
                file_path=file_path,
                line_start=content[:m.start()].count("\n") + 1,
                line_end=content[:m.start()].count("\n") + 1,
            ))

        dependencies: list[IRDependency] = []

        for m in _IMPORT_RE.finditer(content):
            target = next(
                (g for g in m.groups() if g),
                "",
            )

            if target:
                dependencies.append(IRDependency(
                    source_file=file_path,
                    target_module=target,
                    kind="import",
                    line=content[:m.start()].count("\n") + 1,
                ))

        errors: list[str] = []

        is_ts = file_path.endswith((".ts", ".tsx"))
        language = "typescript" if is_ts else "javascript"

        file_node = IRFileNode(
            id=f"file:{file_path}",
            type=NodeType.FILE,
            name=Path(file_path).name,
            source="js-parser",
            file_path=file_path,
            language=language,
            role=FileRole.UNKNOWN,
            line_count=content.count("\n") + 1,
            byte_size=len(content.encode("utf-8")),
            confidence=0.85,
        )

        return IRFileParseResult(
            file_path=file_path,
            language=language,
            file_node=file_node,
            symbols=tuple(symbols),
            dependencies=tuple(dependencies),
            parse_errors=tuple(errors),
            confidence=0.85,
        )
