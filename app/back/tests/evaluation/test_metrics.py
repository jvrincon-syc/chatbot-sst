from __future__ import annotations

from evaluation.extraction_metrics import exact_match_rate
from evaluation.parsing_metrics import page_coverage
from evaluation.retrieval_metrics import mean_reciprocal_rank, recall_at_k


def test_page_coverage_counts_present_pages_over_expected_pages() -> None:
    assert page_coverage(expected_pages=4, parsed_pages=[1, 2, 4]) == 0.75


def test_exact_match_rate_compares_expected_metadata_values() -> None:
    assert exact_match_rate(
        expected={"code": "RE-01", "version": "1"},
        actual={"code": "RE-01", "version": "2"},
    ) == 0.5


def test_retrieval_metrics_compute_recall_and_mrr() -> None:
    ranked = [["a", "b", "c"], ["d", "e"]]
    relevant = [{"c"}, {"x"}]

    assert recall_at_k(ranked, relevant, k=3) == 0.5
    assert mean_reciprocal_rank(ranked, relevant) == 1 / 3 / 2
