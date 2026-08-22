import os
from astra.core.logger import get_logger

logger = get_logger("astra.reader.docs_reader")


class DocsReader:
    SUPPORTED_EXTENSIONS = {".md", ".rst", ".txt", ".html"}

    def __init__(self):
        self._readers = {}

    def register(self, extension, reader):
        self._readers[extension] = reader

    def read(self, file_path, encoding="utf-8"):
        ext = os.path.splitext(file_path)[1].lower()
        reader = self._readers.get(ext)
        if reader:
            return reader.read(file_path, encoding)
        return self._fallback_read(file_path, encoding)

    def _fallback_read(self, file_path, encoding):
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
            return {
                "file_path": file_path,
                "content": content,
                "line_count": content.count("\n") + 1,
            }
        except Exception as e:
            logger.error("Failed to read doc %s: %s", file_path, e)
            return None
