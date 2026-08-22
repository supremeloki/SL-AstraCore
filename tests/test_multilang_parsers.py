from astra.parser.jsts_adapter import JSTSParserAdapter
from astra.parser.markdown_adapter import MarkdownParserAdapter
from astra.parser.registry import ParserRegistry


def test_jsts_parser_extracts_symbols_and_imports():
    adapter = JSTSParserAdapter()

    content = '''
import React from "react"
import { useState } from "react"

export function hello() {}

export const world = () => {}

export class Greeter {}
'''

    result = adapter.parse("app.ts", content)

    assert result.language == "typescript"
    assert len(result.symbols) == 3
    assert len(result.dependencies) == 2


def test_markdown_parser_extracts_headings():
    adapter = MarkdownParserAdapter()

    content = '''
# Architecture
## Decisions
### Runtime
'''

    result = adapter.parse("notes.md", content)

    assert result.language == "markdown"
    assert len(result.vault_concepts) == 3
    assert result.file_node.is_vault is True


def test_registry_multi_language_support():
    registry = ParserRegistry()

    registry.register(JSTSParserAdapter())
    registry.register(MarkdownParserAdapter())

    assert registry.can_parse("main.ts")
    assert registry.can_parse("notes.md")
    assert "javascript" in registry.supported_languages()
    assert "markdown" in registry.supported_languages()
