from collections import defaultdict


class NameNormalizer:
    def normalize_key(self, name: str) -> str:
        return name.lower().replace("_", "").replace("-", "").replace(" ", "")

    def build_alias_map(self, entities: dict[str, list[str]]) -> dict[str, list[str]]:
        normalized = defaultdict(list)

        for name, values in entities.items():
            normalized[self.normalize_key(name)].extend(values)

        return {
            key: values
            for key, values in normalized.items()
            if len(values) > 1
        }
