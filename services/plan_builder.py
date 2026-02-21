from __future__ import annotations

from typing import Any, Dict, Optional

from core.models import Candidate, Task
from core.types import CandidateStatus, StageType


STAGE_ORDER = [
    StageType.scenario,
    StageType.driving_question,
    StageType.question_chain,
    StageType.activity,
    StageType.experiment,
]

CONTENT_KEY_BY_STAGE = {
    StageType.scenario: "scenario",
    StageType.driving_question: "driving_question",
    StageType.question_chain: "question_chain",
    StageType.activity: "activity",
    StageType.experiment: "experiment",
}


def _select_candidate(task: Task, stage: StageType) -> Optional[Candidate]:
    artifact = task.artifacts.get(stage)
    if not artifact:
        return None
    if artifact.selected_candidate_id:
        for candidate in artifact.candidates:
            if candidate.id == artifact.selected_candidate_id:
                return candidate
    for candidate in artifact.candidates:
        if candidate.status == CandidateStatus.selected:
            return candidate
    return None


def build_course_plan(task: Task) -> Dict[str, Any]:
    sections = []
    for stage in STAGE_ORDER:
        selected = _select_candidate(task, stage)
        if selected:
            key = CONTENT_KEY_BY_STAGE.get(stage)
            content = selected.content.get(key) if key else selected.content
            sections.append(
                {
                    "stage": stage.value,
                    "title": selected.title or "",
                    "candidate_id": selected.id,
                    "content": content,
                    "raw": selected.content,
                }
            )
        else:
            sections.append(
                {
                    "stage": stage.value,
                    "title": "",
                    "candidate_id": None,
                    "content": None,
                    "raw": None,
                }
            )
    return {"task_id": task.task_id, "sections": sections}


__all__ = ["build_course_plan"]
