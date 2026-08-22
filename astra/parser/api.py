from __future__ import annotations

from typing import Protocol, Sequence

from astra.ir.models import IRFileParseResult, IRProjectIndex


class ParserAdapter(Protocol):
    language: str

    def supports(self, language: str) -> bool: ...

    def parse_file(self, file_path: str) -> IRFileParseResult: ...


class ParserRegistry(Protocol):
    def register(self, adapter: ParserAdapter) -> None: ...

    def unregister(self, language: str) -> None: ...

    def get(self, language: str) -> ParserAdapter: ...

    def supported_languages(self) -> Sequence[str]: ...


class ParserEngine(Protocol):
    def parse_repository(
        self,
        repository_index: IRProjectIndex,
    ) -> Sequence[IRFileParseResult]: ...
