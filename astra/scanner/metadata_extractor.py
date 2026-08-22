import os

from astra.models.file_node import FileCategory
from astra.models.repository import FileKind, FileMetadata


class MetadataExtractor:
    def __init__(self, root_path, language_detector, binary_detector, hash_engine, max_file_size_kb, hash_algorithm="sha256"):
        self._root = os.path.abspath(root_path)
        self._language_detector = language_detector
        self._binary_detector = binary_detector
        self._hash_engine = hash_engine
        self._max_size_bytes = int(max_file_size_kb * 1024)
        self._hash_algorithm = hash_algorithm

    def extract(self, path, rel_path, category):
        stat = os.lstat(path)
        size = stat.st_size
        if size > self._max_size_bytes:
            return None, "file exceeds max_file_size_kb"

        is_symlink = os.path.islink(path)
        is_binary = self._binary_detector.is_binary(path)
        kind = FileKind.SYMLINK if is_symlink else (FileKind.BINARY if is_binary else FileKind.TEXT)
        extension = os.path.splitext(rel_path)[1].lower()
        language = self._language_detector.detect(rel_path)
        encoding, lines_count = self._text_profile(path, is_binary)
        hash_value = self._hash_engine.hash_file(path)
        file_id = self.deterministic_id(rel_path)

        return FileMetadata(
            id=file_id,
            path=os.path.abspath(path),
            rel_path=rel_path.replace("\\", "/"),
            name=os.path.basename(path),
            extension=extension,
            category=category,
            kind=kind,
            language=language,
            size_bytes=size,
            hash_value=hash_value,
            hash_algorithm=self._hash_algorithm,
            modified_at=stat.st_mtime,
            is_hidden=self._is_hidden(rel_path),
            is_symlink=is_symlink,
            is_binary=is_binary,
            encoding=encoding,
            lines_count=lines_count,
        ), None

    def deterministic_id(self, rel_path):
        normalized = rel_path.replace("\\", "/").lstrip("./").lower()
        return self._hash_engine.hash_string(normalized)

    def _text_profile(self, path, is_binary):
        if is_binary:
            return "", 0
        for encoding in ("utf-8", "latin-1"):
            try:
                with open(path, "r", encoding=encoding) as f:
                    return encoding, sum(1 for _ in f)
            except UnicodeDecodeError:
                continue
            except OSError:
                break
        return "", 0

    def _is_hidden(self, rel_path):
        return any(part.startswith(".") for part in rel_path.replace("\\", "/").split("/"))
