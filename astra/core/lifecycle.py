from enum import Enum


class Phase(Enum):
    DISCOVERY = "discovery"
    CLASSIFICATION = "classification"
    READING = "reading"
    PARSING = "parsing"
    SEMANTIC_TAGGING = "semantic_tagging"
    VAULT_INTEGRATION = "vault_integration"
    INDEX_OUTPUT = "index_output"
    COMPLETE = "complete"


class Lifecycle:
    def __init__(self):
        self._phase = Phase.DISCOVERY
        self._stats = {
            "files_discovered": 0,
            "files_classified": 0,
            "files_read": 0,
            "files_parsed": 0,
            "files_tagged": 0,
            "vault_nodes": 0,
            "errors": 0,
        }

    @property
    def phase(self):
        return self._phase

    def advance(self, phase=None):
        if phase is not None:
            self._phase = Phase(phase)
        else:
            order = list(Phase)
            idx = order.index(self._phase)
            if idx < len(order) - 1:
                self._phase = order[idx + 1]

    def record(self, key, value=1):
        if key in self._stats:
            self._stats[key] += value

    @property
    def stats(self):
        return dict(self._stats)
