from astra.core.logger import get_logger

logger = get_logger("astra.context.token_budget")

AVG_CHARS_PER_TOKEN = 4
MAX_BUDGET = 32000


class TokenBudget:
    def __init__(self, max_budget=MAX_BUDGET):
        self._max = max_budget
        self._used = 0

    @property
    def budget(self):
        return self._max

    @property
    def used(self):
        return self._used

    @property
    def remaining(self):
        return max(0, self._max - self._used)

    @staticmethod
    def estimate(text):
        return max(1, len(text) // AVG_CHARS_PER_TOKEN)

    def reserve(self, _node_id, text, force=False):
        tokens = self.estimate(text)
        if not force and self._used + tokens > self._max:
            return False
        self._used += tokens
        return True

    def can_fit(self, text):
        return self._used + self.estimate(text) <= self._max

    def reset(self):
        self._used = 0

    def set_budget(self, budget):
        self._max = budget
        if self._used > self._max:
            self._used = self._max
