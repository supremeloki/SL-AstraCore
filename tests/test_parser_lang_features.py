import pytest

from astra.ir.models import SymbolKind
from astra.models.file_node import FileCategory
from astra.parser.jsts_adapter import JSTSParserAdapter
from astra.parser.python_adapter import PythonParserAdapter
from astra.parser.universal_parser import UniversalParser


class _FileMeta:
    def __init__(self, rel_path, source):
        self.id = f"file:{rel_path}"
        self.rel_path = rel_path
        self.path = rel_path
        self.language = ""
        self.category = FileCategory.CONFIG
        self.is_binary = False
        self.lines_count = len(source.splitlines())
        self.size_bytes = len(source.encode("utf-8"))
        self.encoding = "utf-8"


@pytest.fixture()
def config_file(tmp_path):
    def _make(rel_path, source):
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        meta = _FileMeta(rel_path, source)
        meta.path = str(path)
        return meta

    return _make


def test_python_adapter_async_and_decorators():
    adapter = PythonParserAdapter()
    content = '''
import functools

@functools.cache
@property
def cached_prop():
    return 1

async def fetch():
    pass

class Repo:
    @staticmethod
    async def load():
        pass
'''
    result = adapter.parse("mod.py", content)

    by_name = {s.name: s for s in result.symbols}
    assert {"cached_prop", "fetch", "Repo", "load"} <= set(by_name)
    assert all(by_name[n].kind == SymbolKind.FUNCTION for n in ("cached_prop", "fetch"))
    assert by_name["Repo"].kind == SymbolKind.CLASS
    assert by_name["cached_prop"].metadata["decorators"] == ["cache", "property"]
    assert by_name["load"].metadata["decorators"] == ["staticmethod"]
    assert "decorators" not in by_name["fetch"].metadata


def test_universal_parser_json_toml_yaml_config_keys(config_file):
    parser = UniversalParser()

    json_meta = config_file("settings.json", '{"server": {"port": 8080}, "name": "demo"}')
    json_parsed = parser.parse_file(json_meta)
    json_keys = [e.name for e in json_parsed.elements if e.kind.value == "config_key"]
    assert set(json_keys) == {"server", "server.port", "name"}

    toml_meta = config_file("pyproject.toml", '[tool]\nname = "demo"\n')
    toml_parsed = parser.parse_file(toml_meta)
    toml_keys = [e.name for e in toml_parsed.elements if e.kind.value == "config_key"]
    assert set(toml_keys) == {"tool", "tool.name"}

    yaml_meta = config_file("astra.yaml", "project:\n  name: demo\n")
    yaml_parsed = parser.parse_file(yaml_meta)
    yaml_keys = [e.name for e in yaml_parsed.elements if e.kind.value == "config_key"]
    assert set(yaml_keys) == {"project", "project.name"}


def test_universal_parser_invalid_json_falls_back(config_file):
    parser = UniversalParser()
    meta = config_file("broken.json", "{not valid")
    parsed = parser.parse_file(meta)
    assert parsed.elements


def test_jsts_adapter_import_forms():
    adapter = JSTSParserAdapter()
    content = '''
import def, { named } from "./combo"
export { re } from "./re-export"
export * from "./star"
const m = import("./dynamic")
'''
    result = adapter.parse("app.ts", content)

    targets = {d.target_module for d in result.dependencies}
    assert targets == {"./combo", "./re-export", "./star", "./dynamic"}
