from __future__ import annotations

from typing import Dict, Set

from core.types import ActionType, StageStatus


MAX_ITERATIONS = 10


ALLOWED_ACTIONS: Dict[StageStatus, Set[ActionType]] = {
    StageStatus.initialized: {
        ActionType.regenerate_candidates,
        ActionType.provide_feedback,
        ActionType.select_candidate,
        ActionType.finalize_stage,
        ActionType.resolve_conflict,
    },
    StageStatus.generating: {
        ActionType.regenerate_candidates,
        ActionType.provide_feedback,
    },
    StageStatus.pending_choice: {
        ActionType.select_candidate,
        ActionType.regenerate_candidates,
        ActionType.provide_feedback,
        ActionType.finalize_stage,
        ActionType.resolve_conflict,
    },
    StageStatus.feedback_loop: {
        ActionType.regenerate_candidates,
        ActionType.provide_feedback,
        ActionType.select_candidate,
        ActionType.finalize_stage,
        ActionType.resolve_conflict,
    },
    StageStatus.modifying: {
        ActionType.regenerate_candidates,
        ActionType.provide_feedback,
        ActionType.select_candidate,
        ActionType.finalize_stage,
        ActionType.resolve_conflict,
    },
    StageStatus.finalized: {
        ActionType.provide_feedback,
        ActionType.regenerate_candidates,
    },
}


def can_apply_action(stage_status: StageStatus, action_type: ActionType) -> bool:
    return action_type in ALLOWED_ACTIONS.get(stage_status, set())


def should_force_exit(iteration_count: int) -> bool:
    return iteration_count >= MAX_ITERATIONS
