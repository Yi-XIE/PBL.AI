import json
from typing import Any, Dict, List


COMPONENT_FILES = {
    "scenario": "course/scenario.md",
    "driving_question": "course/driving_question.md",
    "question_chain": "course/question_chain.md",
    "activity": "course/activity.md",
    "experiment": "course/experiment.md",
}


def _status_for(component: str, state: Dict[str, Any]) -> str:
    pending_component = state.get("pending_component")
    locked_components = state.get("locked_components", []) or []
    validity = state.get("component_validity", {}) or {}
    progress = state.get("design_progress", {}) or {}

    if component == "question_chain":
        if pending_component == "driving_question":
            return "pending"
        if "driving_question" in locked_components:
            return "locked"
    if pending_component == component:
        return "pending"
    if component in locked_components:
        return "locked"
    if validity.get(component) == "INVALID":
        return "invalid"
    if progress.get(component):
        return "valid"
    return "empty"


def _question_chain_text(course_design: Dict[str, Any]) -> str:
    chain = course_design.get("question_chain", []) or []
    return "\n".join(f"- {item}" for item in chain)


def build_virtual_files(state: Dict[str, Any]) -> Dict[str, Any]:
    course_design = state.get("course_design", {}) or {}
    files: List[Dict[str, Any]] = []

    files.append(
        {
            "path": COMPONENT_FILES["scenario"],
            "language": "markdown",
            "editable": True,
            "status": _status_for("scenario", state),
            "content": course_design.get("scenario", "") or "",
        }
    )
    files.append(
        {
            "path": COMPONENT_FILES["driving_question"],
            "language": "markdown",
            "editable": True,
            "status": _status_for("driving_question", state),
            "content": course_design.get("driving_question", "") or "",
        }
    )
    files.append(
        {
            "path": COMPONENT_FILES["question_chain"],
            "language": "markdown",
            "editable": True,
            "status": _status_for("question_chain", state),
            "content": _question_chain_text(course_design),
        }
    )
    files.append(
        {
            "path": COMPONENT_FILES["activity"],
            "language": "markdown",
            "editable": True,
            "status": _status_for("activity", state),
            "content": course_design.get("activity", "") or "",
        }
    )
    files.append(
        {
            "path": COMPONENT_FILES["experiment"],
            "language": "markdown",
            "editable": True,
            "status": _status_for("experiment", state),
            "content": course_design.get("experiment", "") or "",
        }
    )

    files.append(
        {
            "path": "course/course_design.json",
            "language": "json",
            "editable": False,
            "status": "info",
            "content": json.dumps(course_design, ensure_ascii=False, indent=2),
        }
    )

    files.append(
        {
            "path": "debug/context_summary.md",
            "language": "markdown",
            "editable": False,
            "status": "info",
            "content": state.get("context_summary", "") or "",
        }
    )
    files.append(
        {
            "path": "debug/observations.log",
            "language": "text",
            "editable": False,
            "status": "info",
            "content": "\n".join(state.get("observations", []) or []),
        }
    )
    files.append(
        {
            "path": "debug/action_inputs.json",
            "language": "json",
            "editable": False,
            "status": "info",
            "content": json.dumps(state.get("action_inputs", []) or [], ensure_ascii=False, indent=2),
        }
    )

    pending = state.get("pending_component") or state.get("current_component") or ""
    selected_default = COMPONENT_FILES.get(pending, COMPONENT_FILES["scenario"])

    return {"files": files, "selected_default": selected_default}
