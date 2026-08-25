from __future__ import annotations

from abc import abstractmethod
from typing import Protocol

from astra.ir.models import IRFileParseResult


class ParserAdapter(Protocol):
    """Protocol for language-specific parser adapters."""

    @property
    @abstractmethod
    def language(self) -> str: ...

    @property
    @abstractmethod
    def file_extensions(self) -> tuple[str, ...]: ...

    @abstractmethod
    def can_parse(self, file_path: str) -> bool: ...

    @abstractmethod
    def parse(self, file_path: str, content: str) -> IRFileParseResult: ...


class ParserRegistry:
    """Registry for parser adapters with language detection."""

    def __init__(self) -> None:
        self._adapters: dict[str, ParserAdapter] = {}
        self._extension_map: dict[str, ParserAdapter] = {}

    def register(self, adapter: ParserAdapter) -> None:
        self._adapters[adapter.language] = adapter
        for ext in adapter.file_extensions:
            self._extension_map[ext] = adapter

    def get_by_language(self, language: str) -> ParserAdapter | None:
        return self._adapters.get(language)

    def get_by_file_path(self, file_path: str) -> ParserAdapter | None:
        ext = "." + file_path.split(".")[-1] if "." in file_path else ""
        return self._extension_map.get(ext)

    def can_parse(self, file_path: str) -> bool:
        return self.get_by_file_path(file_path) is not None

    def parse(self, file_path: str, content: str) -> IRFileParseResult | None:
        adapter = self.get_by_file_path(file_path)
        if adapter is None:
            return None
        return adapter.parse(file_path, content)

    def supported_languages(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters.keys()))

    def supported_extensions(self) -> tuple[str, ...]:
        return tuple(sorted(self._extension_map.keys()))


_global_registry: ParserRegistry | None = None


def get_parser_registry() -> ParserRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = build_default_parser_registry()
    return _global_registry


_TREE_SITTER_LANGUAGES = ("go", "rust", "java", "c", "cpp", "csharp", "ruby", "php")


def build_default_parser_registry() -> ParserRegistry:
    from astra.parser.jsts_adapter import JSTSParserAdapter
    from astra.parser.markdown_adapter import MarkdownParserAdapter
    from astra.parser.python_adapter import PythonParserAdapter
    from astra.parser.tree_sitter_adapter import TreeSitterAdapter

    registry = ParserRegistry()
    registry.register(PythonParserAdapter())
    registry.register(JSTSParserAdapter())
    registry.register(MarkdownParserAdapter())
    for language in _TREE_SITTER_LANGUAGES:
        adapter = TreeSitterAdapter(language)
        try:
            from tree_sitter_language_pack import get_parser
            if get_parser(language) is not None:
                registry.register(adapter)
        except Exception:
            pass
    return registry