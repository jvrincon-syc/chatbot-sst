from __future__ import annotations


PIPELINE_STATES = [
    "inventoried",
    "uploaded",
    "classifying",
    "classified",
    "parsing",
    "parsed",
    "extracting",
    "extracted",
    "validating",
    "bundled",
    "indexed",
]

RESUME_AFTER = {
    "inventoried": "uploaded",
    "uploaded": "classifying",
    "classified": "parsing",
    "parsed": "extracting",
    "extracted": "validating",
    "bundled": "indexed",
}


class JobResumePlanner:
    def next_state(self, completed_states: list[str]) -> str:
        successful = [state for state in completed_states if state in PIPELINE_STATES]
        if not successful:
            return PIPELINE_STATES[0]
        last = successful[-1]
        return RESUME_AFTER.get(last, _next_after(last))

    def resume_plan(self, completed_states: list[str]) -> list[str]:
        start = self.next_state(completed_states)
        start_index = PIPELINE_STATES.index(start)
        return PIPELINE_STATES[start_index:]


def _next_after(state: str) -> str:
    index = PIPELINE_STATES.index(state)
    if index + 1 >= len(PIPELINE_STATES):
        return PIPELINE_STATES[-1]
    return PIPELINE_STATES[index + 1]
