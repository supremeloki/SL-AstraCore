import os
import fnmatch
from astra.core.constants import ASTRAIGNORE_PATH, DEFAULT_IGNORE_DIRS, DEFAULT_IGNORE_EXTENSIONS
from astra.core.logger import get_logger

logger = get_logger("astra.scanner.ignore_engine")


class IgnoreEngine:
    def __init__(self, root_path):
        self._root = root_path
        self._dir_patterns = set(DEFAULT_IGNORE_DIRS)
        self._ext_patterns = set(DEFAULT_IGNORE_EXTENSIONS)
        self._custom_patterns = []
        self._load_astraignore()

    def _load_astraignore(self):
        ignore_path = os.path.join(self._root, ".astraignore")
        if not os.path.isfile(ignore_path):
            return
        with open(ignore_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                self._custom_patterns.append(line)

    def is_ignored(self, rel_path):
        parts = rel_path.replace("\\", "/").split("/")
        for part in parts:
            if part in self._dir_patterns:
                return True
        for pattern in self._custom_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            for part in parts:
                if fnmatch.fnmatch(part, pattern):
                    return True
        ext = os.path.splitext(rel_path)[1]
        if ext in self._ext_patterns:
            return True
        return False

    def is_ignored_dir(self, dir_name):
        if dir_name in self._dir_patterns:
            return True
        for pattern in self._custom_patterns:
            if fnmatch.fnmatch(dir_name, pattern):
                return True
        return False

    def is_ignored_extension(self, extension):
        return extension in self._ext_patterns
