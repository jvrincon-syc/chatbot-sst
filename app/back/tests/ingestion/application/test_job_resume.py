from __future__ import annotations

from ingestion.application.services.job_resume import JobResumePlanner


def test_job_resume_planner_resumes_after_last_successful_state() -> None:
    planner = JobResumePlanner()

    assert planner.next_state(["inventoried", "uploaded", "parsed"]) == "extracting"


def test_job_resume_planner_does_not_repeat_parse_when_extract_failed() -> None:
    planner = JobResumePlanner()

    assert planner.resume_plan(["inventoried", "uploaded", "parsed", "failed"]) == [
        "extracting",
        "extracted",
        "validating",
        "bundled",
        "indexed",
    ]
