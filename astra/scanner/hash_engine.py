import hashlib
from astra.core.logger import get_logger

logger = get_logger("astra.scanner.hash_engine")


class HashEngine:
    def __init__(self, algorithm="sha256", buffer_size=65536):
        self._algorithm = algorithm
        self._buffer_size = buffer_size

    def hash_file(self, file_path):
        h = hashlib.new(self._algorithm)
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(self._buffer_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def hash_bytes(self, data):
        return hashlib.new(self._algorithm, data).hexdigest()

    def hash_string(self, text):
        return hashlib.new(self._algorithm, text.encode("utf-8")).hexdigest()
