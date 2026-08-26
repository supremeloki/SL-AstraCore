from __future__ import annotations

from pathlib import Path

from astra.core.logger import get_logger
from astra.ir.models import (
    FileRole,
    IRDependency,
    IRFileNode,
    IRFileParseResult,
    IRSymbol,
    NodeType,
    SymbolKind,
)

logger = get_logger("astra.parser.tree_sitter_adapter")

_NAME_NODE_TYPES = frozenset({
    "identifier", "name", "type_identifier", "constant", "property_identifier",
})

_FUNCTION_NODES = frozenset({
    "function_declaration", "function_item", "function_definition",
    "method_declaration", "method_definition", "method", "function_signature",
})

_CLASS_NODES = frozenset({
    "class_declaration", "class_specifier", "struct_item", "class",
})

_IMPORT_NODES = {
    "go": ("import_spec",),
    "rust": ("use_declaration",),
    "java": ("import_declaration",),
    "csharp": ("using_directive",),
    "c": ("preproc_include",),
    "cpp": ("preproc_include",),
    "ruby": ("call",),
}

_LANG_EXTENSIONS = {
    "go": (".go",),
    "rust": (".rs",),
    "java": (".java",),
    "c": (".c", ".h"),
    "cpp": (".cpp", ".cc", ".cxx", ".hpp", ".hh"),
    "csharp": (".cs",),
    "ruby": (".rb",),
    "php": (".php",),
}


def _get_parser(language: str):
    try:
        from typing import cast
        from tree_sitter_language_pack import get_parser, SupportedLanguage
        return get_parser(cast(SupportedLanguage, language))
    except Exception:
        return None


def _find_name(node, source: str) -> str:
    # Java/C# method_declaration puts the return type (type_identifier) before
    # the name; prefer a direct identifier/name child, fall back to recursion.
    for child in node.named_children:
        if child.type in ("identifier", "name", "property_identifier"):
            return source[child.start_byte:child.end_byte]
    for child in node.named_children:
        if child.type in ("type_identifier", "constant",):
            return source[child.start_byte:child.end_byte]
    for child in node.named_children:
        name = _find_name(child, source)
        if name:
            return name
    return ""


def _walk(node):
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _strip_quotes(text: str) -> str:
    return text.strip().strip('"').strip("'")


class TreeSitterAdapter:
    """Generic tree-sitter adapter; one instance per language."""

    def __init__(self, language: str) -> None:
        self.language = language
        self.file_extensions = _LANG_EXTENSIONS[language]
        self._parser = None

    def can_parse(self, file_path: str) -> bool:
        return file_path.endswith(self.file_extensions)

    def parse(self, file_path: str, content: str) -> IRFileParseResult:
        symbols: list[IRSymbol] = []
        dependencies: list[IRDependency] = []
        errors: list[str] = []

        if self._parser is None:
            self._parser = _get_parser(self.language)
        parser = self._parser

        try:
            if parser is None:
                raise RuntimeError(f"tree-sitter parser unavailable for {self.language}")
            tree = parser.parse(content.encode("utf-8"))

            import_nodes = _IMPORT_NODES.get(self.language, ())
            for node in _walk(tree.root_node):
                if node.type in _FUNCTION_NODES:
                    name = _find_name(node, content)
                    if name:
                        symbols.append(IRSymbol(
                            name=name,
                            kind=SymbolKind.FUNCTION,
                            file_path=file_path,
                            line_start=node.start_point[0] + 1,
                            line_end=node.end_point[0] + 1,
                        ))
                elif node.type in _CLASS_NODES:
                    name = _find_name(node, content)
                    if name:
                        symbols.append(IRSymbol(
                            name=name,
                            kind=SymbolKind.CLASS,
                            file_path=file_path,
                            line_start=node.start_point[0] + 1,
                            line_end=node.end_point[0] + 1,
                        ))
                elif node.type in import_nodes and self.language != "ruby":
                    dependencies.append(IRDependency(
                        source_file=file_path,
                        target_module=_strip_quotes(content[node.start_byte:node.end_byte]),
                        kind="import",
                        line=node.start_point[0] + 1,
                    ))
                elif self.language == "ruby" and node.type == "call":
                    callee = node.named_children[0] if node.named_children else None
                    callee_name = content[callee.start_byte:callee.end_byte] if callee is not None else ""
                    if callee_name in ("require", "require_relative"):
                        args = node.child_by_field_name("arguments")
                        # argument_list spans e.g. ("json"); take the inner string token.
                        target = ""
                        if args is not None:
                            for tok in args.named_children:
                                if tok.type == "string":
                                    inner = [c for c in tok.named_children if c.type == "string_content"]
                                    if inner:
                                        target = content[inner[0].start_byte:inner[0].end_byte]
                                    break
                        if target:
                            dependencies.append(IRDependency(
                                source_file=file_path,
                                target_module=target,
                                kind="import",
                                line=node.start_point[0] + 1,
                            ))
        except Exception as exc:
            errors.append(str(exc))

        confidence = 0.8 if not errors else 0.4
        file_node = IRFileNode(
            id=f"file:{file_path}",
            type=NodeType.FILE,
            name=Path(file_path).name,
            source=f"tree-sitter-{self.language}",
            file_path=file_path,
            language=self.language,
            role=FileRole.UNKNOWN,
            line_count=content.count("\n") + 1,
            byte_size=len(content.encode("utf-8")),
            confidence=confidence,
        )

        return IRFileParseResult(
            file_path=file_path,
            language=self.language,
            file_node=file_node,
            symbols=tuple(symbols),
            dependencies=tuple(dependencies),
            parse_errors=tuple(errors),
            confidence=confidence,
        )
