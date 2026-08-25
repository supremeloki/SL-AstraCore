from __future__ import annotations

import ast
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


def _decorator_names(node):
    names = []
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Attribute):
            names.append(target.attr)
        elif isinstance(target, ast.Name):
            names.append(target.id)
    return names


class PythonParserAdapter:
    language = "python"
    file_extensions = (".py",)

    def can_parse(self, file_path: str) -> bool:
        return file_path.endswith(".py")

    def parse(self, file_path: str, content: str) -> IRFileParseResult:
        symbols: list[IRSymbol] = []
        dependencies: list[IRDependency] = []
        errors: list[str] = []

        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    decorators = _decorator_names(node)
                    symbols.append(
                        IRSymbol(
                            name=node.name,
                            kind=SymbolKind.FUNCTION,
                            file_path=file_path,
                            line_start=node.lineno,
                            line_end=getattr(node, "end_lineno", node.lineno),
                            is_private=node.name.startswith("_"),
                            metadata={"decorators": decorators} if decorators else {},
                        )
                    )

                elif isinstance(node, ast.ClassDef):
                    symbols.append(
                        IRSymbol(
                            name=node.name,
                            kind=SymbolKind.CLASS,
                            file_path=file_path,
                            line_start=node.lineno,
                            line_end=getattr(node, "end_lineno", node.lineno),
                        )
                    )

                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        dependencies.append(
                            IRDependency(
                                source_file=file_path,
                                target_module=alias.name,
                                kind="import",
                                line=node.lineno,
                            )
                        )

                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    dependencies.append(
                        IRDependency(
                            source_file=file_path,
                            target_module=module,
                            kind="import",
                            line=node.lineno,
                        )
                    )

        except SyntaxError as exc:
            errors.append(str(exc))

        file_node = IRFileNode(
            id=f"file:{file_path}",
            type=NodeType.FILE,
            name=Path(file_path).name,
            source="python-parser",
            file_path=file_path,
            language="python",
            role=FileRole.UNKNOWN,
            line_count=content.count("\n") + 1,
            byte_size=len(content.encode("utf-8")),
            confidence=0.95 if not errors else 0.5,
        )

        return IRFileParseResult(
            file_path=file_path,
            language="python",
            file_node=file_node,
            symbols=tuple(symbols),
            dependencies=tuple(dependencies),
            parse_errors=tuple(errors),
            confidence=0.95 if not errors else 0.5,
        )
