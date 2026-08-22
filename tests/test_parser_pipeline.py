from astra.parser.python_adapter import PythonParserAdapter
from astra.parser.registry import get_parser_registry


def test_python_adapter_parses_basic_file():
    adapter = PythonParserAdapter()
    content = """
import os

def hello():
    return "world"

class Greeter:
    def greet(self):
        return hello()
"""
    result = adapter.parse("test.py", content)

    assert result.file_node is not None
    assert len(result.symbols) == 3  # hello, greet, Greeter
    assert len(result.dependencies) == 1  # os
    assert result.language == "python"


def test_registry_integration():
    registry = get_parser_registry()
    adapter = PythonParserAdapter()
    registry.register(adapter)

    assert registry.can_parse("test.py")
    assert registry.get_by_file_path("test.py") == adapter
    assert "python" in registry.supported_languages()
