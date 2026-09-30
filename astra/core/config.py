import os
from astra.core.constants import ROOT_DIR

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

# Only keys the code actually reads. Dead knobs were removed rather than left
# as decoration: a config key nothing reads is a lie about what is configurable.
_DEFAULTS = {
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
    "storage": {"engine": "duckdb"},
    "agent": {"providers": ["generic"]},
}


_MISSING = object()


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
                # A section named in the file replaces that whole default
                # section, so a sibling the file never mentioned has to fall
                # back to the default tree — looked up from the root, not from
                # the segment that was missing, or "scanner.hash_algorithm"
                # would search for a top-level "hash_algorithm".
                fallback = self._default_get(key, _MISSING)
                return default if fallback is _MISSING else fallback
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
