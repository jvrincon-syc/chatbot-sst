from __future__ import annotations

import pytest

from ingestion.application.services.credit_budget import (
    CreditBudget,
    CreditBudgetExceededError,
)


def test_credit_budget_allows_jobs_within_limit_and_records_usage() -> None:
    budget = CreditBudget(max_credits=10)

    budget.reserve(document_id="doc_1", capability="parse", estimated_credits=4)
    budget.record_actual(document_id="doc_1", capability="parse", actual_credits=3)

    assert budget.remaining_credits == 7


def test_credit_budget_stops_new_jobs_when_limit_would_be_exceeded() -> None:
    budget = CreditBudget(max_credits=5)
    budget.reserve(document_id="doc_1", capability="parse", estimated_credits=4)

    with pytest.raises(CreditBudgetExceededError):
        budget.reserve(document_id="doc_2", capability="extract", estimated_credits=2)
