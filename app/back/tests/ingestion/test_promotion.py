import pytest

from ingestion.promotion import PromotionError, promote_candidate


def test_promotion_rejects_failed_gates_and_leaves_live_unchanged(tmp_path) -> None:
    candidate = tmp_path / "candidate"
    live = tmp_path / "live"
    candidate.mkdir()
    live.mkdir()
    (candidate / "new.txt").write_text("new", encoding="utf-8")
    (live / "old.txt").write_text("old", encoding="utf-8")

    with pytest.raises(PromotionError):
        promote_candidate(candidate, live, {"structural_status": "passed", "golden_status": "failed"})

    assert (live / "old.txt").read_text(encoding="utf-8") == "old"
    assert not (live / "new.txt").exists()


def test_promotion_swaps_candidate_and_removes_stale_live_files(tmp_path) -> None:
    candidate = tmp_path / "candidate"
    live = tmp_path / "live"
    candidate.mkdir()
    live.mkdir()
    (candidate / "new.txt").write_text("new", encoding="utf-8")
    (live / "stale.txt").write_text("stale", encoding="utf-8")

    promote_candidate(candidate, live, {"structural_status": "passed", "golden_status": "passed"})

    assert (live / "new.txt").read_text(encoding="utf-8") == "new"
    assert not (live / "stale.txt").exists()
