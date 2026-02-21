from __future__ import annotations

from core.dependencies import topo_sort_missing_chain
from core.models import DecisionResult, Explanation, Task


def dry_run_next_steps(task: Task) -> DecisionResult:
    if task.current_stage is None:
        return DecisionResult(
            next_stage=None,
            direction="stay",
            explanation=Explanation(summary="No current stage available.", details=[]),
            user_message="No current stage available.",
        )

    try:
        missing_chain = topo_sort_missing_chain(
            task.current_stage,
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
    if missing_chain:
        return DecisionResult(
            next_stage=missing_chain[0],
            direction="backward_completion",
            explanation=Explanation(
                summary="Missing dependency chain.",
                details=[", ".join([s.value for s in missing_chain])],
            ),
            user_message="Please complete prerequisite stages first.",
            constraints={"missing_chain": [s.value for s in missing_chain]},
        )

    return DecisionResult(
        next_stage=task.current_stage,
        direction="forward",
        explanation=Explanation(summary="Ready to proceed.", details=[]),
        user_message="Ready to proceed.",
    )
