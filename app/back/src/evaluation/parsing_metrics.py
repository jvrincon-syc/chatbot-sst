from __future__ import annotations


def page_coverage(*, expected_pages: int, parsed_pages: list[int]) -> float:
    if expected_pages <= 0:
        return 0.0
    return len(set(parsed_pages)) / expected_pages
