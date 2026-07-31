"""Bounded string writer used by complete-render probes."""


class BudgetExceeded(Exception):
    """Raised when a bounded writer cannot accept another fragment."""


class BoundedWriter:
    """Collect fragments without ever retaining more than ``limit`` characters."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._parts: list[str] = []
        self._length = 0

    def write(self, fragment: str) -> None:
        if self._length + len(fragment) > self.limit:
            raise BudgetExceeded
        self._parts.append(fragment)
        self._length += len(fragment)

    @property
    def remaining(self) -> int:
        """Characters that can still be accepted."""
        return self.limit - self._length

    def getvalue(self) -> str:
        return "".join(self._parts)
