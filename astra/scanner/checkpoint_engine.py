import json
import os


class CheckpointEngine:
    def __init__(self, checkpoint_path=None, every=1000):
        self.path = checkpoint_path
        self.every = every
        self._files = {}

    def load(self):
        return set(self.load_state().keys())

    def load_state(self):
        if not self.path or not os.path.isfile(self.path):
            self._files = {}
            return {}
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "files" in data:
            self._files = {
                self._normalize(path): dict(state)
                for path, state in data.get("files", {}).items()
            }
            return dict(self._files)

        # Backward compatibility for v1 checkpoints that only stored paths.
        self._files = {
            self._normalize(path): {"rel_path": self._normalize(path)}
            for path in data.get("seen", [])
        }
        return dict(self._files)

    def mark(self, rel_path, count):
        self.mark_file_path(rel_path, count)

    def mark_file(self, file_metadata, count):
        if not self.path:
            return
        rel_path = self._normalize(file_metadata.rel_path)
        self._files[rel_path] = {
            "id": file_metadata.id,
            "rel_path": rel_path,
            "hash_value": file_metadata.hash_value,
            "hash_algorithm": file_metadata.hash_algorithm,
            "size_bytes": file_metadata.size_bytes,
            "modified_at": file_metadata.modified_at,
        }
        if count % self.every == 0:
            self.save()

    def mark_file_path(self, rel_path, count):
        if not self.path:
            return
        rel_path = self._normalize(rel_path)
        self._files.setdefault(rel_path, {"rel_path": rel_path})
        if count % self.every == 0:
            self.save()

    def is_unchanged(self, file_metadata):
        current = {
            "hash_value": file_metadata.hash_value,
            "hash_algorithm": file_metadata.hash_algorithm,
            "size_bytes": file_metadata.size_bytes,
        }
        previous = self._files.get(self._normalize(file_metadata.rel_path), {})
        return all(previous.get(key) == value for key, value in current.items())

    def deleted_paths(self, current_paths):
        normalized_current = {self._normalize(path) for path in current_paths}
        return sorted(path for path in self._files if path not in normalized_current)

    def retain_only(self, current_paths):
        normalized_current = {self._normalize(path) for path in current_paths}
        self._files = {
            path: state
            for path, state in self._files.items()
            if path in normalized_current
        }

    def save(self):
        if not self.path:
            return
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp_path = f"{self.path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"version": 2, "files": self._files}, f, indent=2, sort_keys=True)
        os.replace(tmp_path, self.path)

    def _normalize(self, rel_path):
        return (rel_path or "").replace("\\", "/")
