import os
from astra.core.constants import ROOT_DIR

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

_DEFAULTS = {
    "project": {"name": "SL-AstraCore", "version": "1.0.0"},
    "scanner": {
        "max_file_size_kb": 1024,
        "follow_symlinks": False,
        "respect_astraignore": True,
        "include_hidden": True,
        "worker_count": 1,
        "streaming_buffer": 65536,
        "hash_algorithm": "sha256",
        "checkpoint_path": "",
        "checkpoint_every": 1000,
    },
    "parser": {
        "languages": [
            "python", "javascript", "typescript", "go", "rust",
            "java", "c", "cpp", "csharp", "ruby",
        ],
        "fallback_on_unknown": True,
    },
    "reader": {
        "line_by_line": True,
        "preserve_order": True,
        "max_lines_per_file": 250000,
    },
    "vault": {
        "enabled": True,
        "detect_frontmatter": True,
        "parse_wikilinks": True,
        "parse_tags": True,
    },
    "storage": {"engine": "duckdb", "cache_engine": "sqlite"},
    "dashboard": {"host": "0.0.0.0", "port": 8470},
    "logging": {
        "level": "INFO",
        "format": "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    },
}


class Config:
    def __init__(self, path=None):
        self._raw = {}
        self._project_path = path or ROOT_DIR
        self._load()

    def _load(self):
        config_path = os.path.join(self._project_path, "astra.yaml")
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
                self._raw = self._load_yaml(content)
        else:
            self._raw = {}

    def _load_yaml(self, content):
        if yaml is not None:
            return yaml.safe_load(content) or {}
        return self._simple_yaml(content)

    def _simple_yaml(self, content):
        root = {}
        stack = [(0, root)]
        for raw_line in content.splitlines():
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue
            indent = len(raw_line) - len(raw_line.lstrip(" "))
            line = raw_line.strip()
            if ":" not in line or line.startswith("- "):
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip("\"'")
            while stack and indent < stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            if value == "":
                child = {}
                parent[key] = child
                stack.append((indent + 2, child))
            else:
                parent[key] = self._coerce_value(value)
        return root

    def _coerce_value(self, value):
        lower = value.lower()
        if lower == "true":
            return True
        if lower == "false":
            return False
        try:
            return int(value)
        except ValueError:
            return value

    def get(self, key, default=None):
        keys = key.split(".")
        node = self._raw
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                keys_remaining = ".".join(keys[keys.index(k):])
                return self._default_get(keys_remaining, default)
        return node

    def _default_get(self, key, default):
        keys = key.split(".")
        node = _DEFAULTS
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return default
        return node

    @property
    def project_path(self):
        return self._project_path

    @property
    def raw(self):
        return dict(self._raw)
