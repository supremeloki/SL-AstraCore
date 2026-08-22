import json
from dataclasses import asdict, is_dataclass
from enum import Enum


class ExportEngine:
    def to_dict(self, repository_index):
        return self._convert(repository_index)

    def to_json(self, repository_index, indent=2):
        return json.dumps(self.to_dict(repository_index), indent=indent, sort_keys=True)

    def write_json(self, repository_index, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(self.to_json(repository_index))

    def write_jsonl(self, items, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(self._convert(item), sort_keys=True))
                f.write("\n")

    def _convert(self, value):
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return {k: self._convert(v) for k, v in asdict(value).items()}
        if isinstance(value, list):
            return [self._convert(v) for v in value]
        if isinstance(value, dict):
            return {k: self._convert(v) for k, v in value.items()}
        return value
