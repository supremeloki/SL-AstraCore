import json
import os

from astra.scanner.export_engine import ExportEngine


class RepositoryIndexStore:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self._export = ExportEngine()

    def save(self, repository_index):
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp_path = f"{self.path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._export.to_dict(repository_index), f, indent=2, sort_keys=True)
        os.replace(tmp_path, self.path)
        return self.path

    def load_dict(self):
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def exists(self):
        return os.path.isfile(self.path)
