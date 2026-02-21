from __future__ import annotations

from typing import Optional

from core.dependencies import STAGE_SEQUENCE, topo_sort_missing_chain
from core.models import DecisionResult, Explanation, Task
from core.types import StageType


def next_required_stage(task: Task) -> Optional[StageType]:
    for stage in STAGE_SEQUENCE:
        if stage not in task.completed_stages:
            return stage
    return None


def make_decision(
    task: Task,
    target_stage: Optional[StageType] = None,
    requested_action: Optional[str] = None,
) -> DecisionResult:
    if task.status == "completed":
        return DecisionResult(
            next_stage=None,
            direction="stay",
            explanation=Explanation(summary="Task already completed.", details=[]),
            user_message="Task is already completed.",
        )

    stage_to_check = target_stage or task.current_stage or next_required_stage(task)
    if stage_to_check is None:
        return DecisionResult(
            next_stage=None,
            direction="stay",
            explanation=Explanation(summary="No remaining stages.", details=[]),
            user_message="No remaining stages.",
        )

    try:
        missing_chain = topo_sort_missing_chain(
            stage_to_check,
            task.entry_point,
            task.completed_stages,
        )
    except ValueError as exc:
        return DecisionResult(
            next_stage=None,
            direction="error",
            explanation=Explanation(summary=str(exc), details=[]),
            user_message="Dependency cycle detected. Please review the dependency table.",
            constraints={"error": "dependency_cycle"},
        )

    if missing_chain and missing_chain[0] != stage_to_check:
        missing_labels = ", ".join([stage.value for stage in missing_chain])
        explanation = Explanation(
            summary="Missing dependencies detected.",
            details=[f"Missing chain: {missing_labels}"],
        )
        return DecisionResult(
            next_stage=missing_chain[0],
            direction="backward_completion",
            explanation=explanation,
            user_message="Please complete prerequisite stages first.",
            constraints={"missing_chain": [s.value for s in missing_chain]},
        )

    return DecisionResult(
        next_stage=stage_to_check,
        direction="forward",
        explanation=Explanation(
            summary="Ready to proceed.",
            details=[f"Requested action: {requested_action or 'none'}"],
        ),
        user_message="Ready to proceed.",
    )
