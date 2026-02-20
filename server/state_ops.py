import json
import re
from typing import Any, Dict, List, Tuple


def build_user_input(user_input: str, topic: str, grade_level: str, duration: int) -> str:
    if user_input:
        return user_input
    if topic:
        return f"Design a PBL course on '{topic}' for grade {grade_level}, {duration} minutes."
    return ""


def parse_question_chain(content: str) -> List[str]:
    text = (content or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
    except json.JSONDecodeError:
        pass

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result: List[str] = []
    for line in lines:
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        cleaned = line.strip()
        if cleaned:
            result.append(cleaned)
    return result


def _invalidate_component(state: Dict[str, Any], component: str) -> None:
    course_design = state.get("course_design", {})
    design_progress = state.get("design_progress", {})
    component_validity = state.get("component_validity", {})
    locked_components = state.get("locked_components", []) or []

    if component == "driving_question":
        course_design["driving_question"] = ""
        course_design["question_chain"] = []
        design_progress["driving_question"] = False
        design_progress["question_chain"] = False
        component_validity["driving_question"] = "INVALID"
        component_validity["question_chain"] = "INVALID"
    elif component == "question_chain":
        course_design["question_chain"] = []
        design_progress["question_chain"] = False
        component_validity["question_chain"] = "INVALID"
    else:
        course_design[component] = ""
        design_progress[component] = False
        component_validity[component] = "INVALID"

    if component in locked_components:
        locked_components.remove(component)
    if component == "question_chain" and "driving_question" in locked_components:
        locked_components.remove("driving_question")

    state["course_design"] = course_design
    state["design_progress"] = design_progress
    state["component_validity"] = component_validity
    state["locked_components"] = locked_components


def apply_cascade_reset(state: Dict[str, Any], target: str) -> None:
    cascade_map = {
        "scenario": ["driving_question", "question_chain", "activity", "experiment"],
        "driving_question": ["question_chain", "activity", "experiment"],
        "question_chain": ["activity", "experiment"],
        "activity": ["experiment"],
        "experiment": [],
    }
    for component in cascade_map.get(target, []):
        _invalidate_component(state, component)


def _mark_component_validity(state: Dict[str, Any], component: str, valid: bool) -> None:
    component_validity = state.get("component_validity", {})
    component_validity[component] = "VALID" if valid else "EMPTY"
    state["component_validity"] = component_validity


def apply_file_update(
    state: Dict[str, Any],
    path: str,
    content: str,
    cascade: bool = True,
    lock: bool = True,
) -> Tuple[Dict[str, Any], str]:
    course_design = state.get("course_design", {})
    design_progress = state.get("design_progress", {})
    locked_components = state.get("locked_components", []) or []

    component = None
    if path.endswith("scenario.md"):
        component = "scenario"
        course_design["scenario"] = content
        design_progress["scenario"] = bool(content.strip())
        _mark_component_validity(state, "scenario", design_progress["scenario"])
    elif path.endswith("driving_question.md"):
        component = "driving_question"
        course_design["driving_question"] = content
        design_progress["driving_question"] = bool(content.strip())
        _mark_component_validity(state, "driving_question", design_progress["driving_question"])
    elif path.endswith("question_chain.md"):
        component = "question_chain"
        chain = parse_question_chain(content)
        course_design["question_chain"] = chain
        design_progress["question_chain"] = bool(chain)
        _mark_component_validity(state, "question_chain", design_progress["question_chain"])
    elif path.endswith("activity.md"):
        component = "activity"
        course_design["activity"] = content
        design_progress["activity"] = bool(content.strip())
        _mark_component_validity(state, "activity", design_progress["activity"])
    elif path.endswith("experiment.md"):
        component = "experiment"
        course_design["experiment"] = content
        design_progress["experiment"] = bool(content.strip())
        _mark_component_validity(state, "experiment", design_progress["experiment"])
    else:
        raise ValueError(f"Unknown file path: {path}")

    if lock:
        lock_target = "driving_question" if component == "question_chain" else component
        if lock_target and lock_target not in locked_components:
            locked_components.append(lock_target)

    state["course_design"] = course_design
    state["design_progress"] = design_progress
    state["locked_components"] = locked_components

    if cascade and component:
        apply_cascade_reset(state, component)

    state["await_user"] = False
    state["pending_component"] = None
    state["pending_preview"] = {}
    state["user_decision"] = None
    state["feedback_target"] = None

    observations = state.get("observations", []) or []
    observations.append(f"[editor] updated {component}")
    state["observations"] = observations

    return state, component or ""
