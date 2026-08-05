from __future__ import annotations

from dataclasses import dataclass


class CreditBudgetExceededError(RuntimeError):
    """New provider jobs would exceed the configured credit budget."""


@dataclass(frozen=True)
class CreditUsage:
    document_id: str
    capability: str
    estimated_credits: int
    actual_credits: int | None = None


class CreditBudget:
    def __init__(self, *, max_credits: int) -> None:
        if max_credits < 0:
            raise ValueError("max_credits must be non-negative")
        self._max_credits = max_credits
        self._usage: dict[tuple[str, str], CreditUsage] = {}

    @property
    def remaining_credits(self) -> int:
        return self._max_credits - self._committed_credits()

    def reserve(
        self,
        *,
        document_id: str,
        capability: str,
        estimated_credits: int,
    ) -> None:
        if estimated_credits < 0:
            raise ValueError("estimated_credits must be non-negative")
        if self._committed_credits() + estimated_credits > self._max_credits:
            raise CreditBudgetExceededError("credit budget would be exceeded")
        self._usage[(document_id, capability)] = CreditUsage(
            document_id=document_id,
            capability=capability,
            estimated_credits=estimated_credits,
        )

    def record_actual(
        self,
        *,
        document_id: str,
        capability: str,
        actual_credits: int,
    ) -> None:
        if actual_credits < 0:
            raise ValueError("actual_credits must be non-negative")
        key = (document_id, capability)
        usage = self._usage[key]
        self._usage[key] = CreditUsage(
            document_id=usage.document_id,
            capability=usage.capability,
            estimated_credits=usage.estimated_credits,
            actual_credits=actual_credits,
        )

    def _committed_credits(self) -> int:
        return sum(
            usage.actual_credits
            if usage.actual_credits is not None
            else usage.estimated_credits
            for usage in self._usage.values()
        )
