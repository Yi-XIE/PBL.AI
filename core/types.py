from enum import Enum


class StageType(str, Enum):
    tool_seed = "tool_seed"
    scenario = "scenario"
    driving_question = "driving_question"
    question_chain = "question_chain"
    activity = "activity"
    experiment = "experiment"


class EntryPoint(str, Enum):
    scenario = "scenario"
    tool_seed = "tool_seed"


class CandidateStatus(str, Enum):
    generated = "generated"
    frozen = "frozen"
    selected = "selected"


class StageStatus(str, Enum):
    initialized = "initialized"
    generating = "generating"
    pending_choice = "pending_choice"
    feedback_loop = "feedback_loop"
    modifying = "modifying"
    finalized = "finalized"


class ConflictSeverity(str, Enum):
    blocking = "blocking"
    warning = "warning"
    info = "info"


class ActionType(str, Enum):
    select_candidate = "select_candidate"
    regenerate_candidates = "regenerate_candidates"
    provide_feedback = "provide_feedback"
    finalize_stage = "finalize_stage"
    resolve_conflict = "resolve_conflict"
