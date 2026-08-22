from astra.core.logger import get_logger
from astra.models.file_node import FileNode

logger = get_logger("astra.reader.code_reader")


class CodeReader:
    def __init__(self, max_lines=None):
        self._max_lines = max_lines

    def read(self, file_node):
        file_node.status = file_node.status.__class__.READING
        lines = []
        try:
            with open(file_node.path, "r", encoding=file_node.encoding) as f:
                for i, line in enumerate(f, 1):
                    if self._max_lines and i > self._max_lines:
                        break
                    lines.append((i, line))
        except Exception as e:
            file_node.status = file_node.status.__class__.ERROR
            file_node.metadata["error"] = str(e)
            logger.error("Failed to read %s: %s", file_node.path, e)
            return None
        file_node.status = file_node.status.__class__.READ
        file_node.lines_count = len(lines)
        return {
            "file_path": file_node.path,
            "rel_path": file_node.rel_path,
            "language": file_node.language,
            "lines": lines,
            "total_lines": len(lines),
        }

    def read_raw(self, file_node):
        try:
            with open(file_node.path, "r", encoding=file_node.encoding) as f:
                return f.read()
        except Exception as e:
            logger.error("Failed to read raw %s: %s", file_node.path, e)
            return ""
