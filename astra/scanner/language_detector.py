import os
from astra.core.constants import LANGUAGE_MAP
from astra.core.logger import get_logger

logger = get_logger("astra.scanner.language_detector")


class LanguageDetector:
    def __init__(self):
        self._map = dict(LANGUAGE_MAP)

    def detect(self, file_path):
        ext = os.path.splitext(file_path)[1].lower()
        return self._map.get(ext)

    def is_source(self, file_path):
        return self.detect(file_path) is not None

    def is_code(self, file_path):
        lang = self.detect(file_path)
        code_languages = {
            "python", "javascript", "typescript", "go", "rust",
            "java", "kotlin", "swift", "c", "cpp", "csharp",
            "ruby", "php", "lua", "r", "shell",
        }
        return lang in code_languages

    def is_parseable(self, file_path, supported=None):
        lang = self.detect(file_path)
        if lang is None:
            return False
        if supported is None:
            return True
        return lang in supported
