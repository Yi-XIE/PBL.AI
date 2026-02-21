from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.dependencies import compute_missing_deps, topo_sort_missing_chain
from core.models import DecisionResult, Explanation, Task
from core.types import EntryPoint, StageType


@dataclass
class GenerateCandidatesCommand:
    stage: StageType
    count: int = 3
    feedback: Optional[str] = None


def entry_node(task: Task) -> dict:
    return {"task_id": task.task_id, "entry_point": task.entry_point.value}


def dependency_check_node(task: Task, target_stage: StageType) -> dict:
    try:
        missing_chain = topo_sort_missing_chain(
            target_stage,
            task.entry_point,
            task.completed_stages,
        )
    except ValueError as exc:
        return {
            "can_proceed": False,
            "missing": [],
            "required": [],
            "error": str(exc),
        }
    required = compute_missing_deps(target_stage, task.entry_point, [])
    can_proceed = not missing_chain or (len(missing_chain) == 1 and missing_chain[0] == target_stage)
    return {
        "can_proceed": can_proceed,
        "missing": missing_chain,
        "required": required,
    }


def require_previous_stage(task: Task, missing: List[StageType]) -> DecisionResult:
    if not missing:
        return DecisionResult(next_stage=task.current_stage, direction="forward")
    explanation = Explanation(
        summary="Dependencies missing.",
        details=[f"Missing stages: {', '.join([m.value for m in missing])}"],
    )
    return DecisionResult(
        next_stage=missing[0],
        direction="backward_completion",
        explanation=explanation,
        user_message="Please complete prerequisite stages first.",
        constraints={"missing_chain": [m.value for m in missing]},
    )


def candidate_stage_node(task: Task, stage_to_generate: StageType) -> GenerateCandidatesCommand:
    return GenerateCandidatesCommand(stage=stage_to_generate, count=3)


def user_choice_gate(task: Task, action: str) -> dict:
    return {"action": action, "locked": True, "stage": task.current_stage.value}


def stage_finalize_node(task: Task) -> dict:
    return {"stage": task.current_stage.value, "finalized": True}
