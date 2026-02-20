import os
from datetime import datetime
from typing import Any, Dict, List


APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")


def _question_chain_text(course_design: Dict[str, Any]) -> str:
    chain = course_design.get("question_chain", []) or []
    return "\n".join(f"- {item}" for item in chain)


def _course_design_markdown(course_design: Dict[str, Any]) -> str:
    lines: List[str] = [
        "# Course Design",
        "",
        "## Scenario",
        course_design.get("scenario", "") or "_(empty)_",
        "",
        "## Driving Question",
        course_design.get("driving_question", "") or "_(empty)_",
        "",
        "## Question Chain",
    ]
    chain = course_design.get("question_chain", []) or []
    if chain:
        lines.extend([f"- {item}" for item in chain])
    else:
        lines.append("_(empty)_")
    lines.extend(
        [
            "",
            "## Activity",
            course_design.get("activity", "") or "_(empty)_",
            "",
            "## Experiment",
            course_design.get("experiment", "") or "_(empty)_",
        ]
    )
    return "\n".join(lines)


def write_generation_snapshot(session_id: str, state: Dict[str, Any], generation_index: int) -> str:
    course_design = state.get("course_design", {}) or {}
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    session_dir = os.path.join(OUTPUT_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    gen_dir = os.path.join(session_dir, f"gen_{generation_index:03d}_{timestamp}")
    os.makedirs(gen_dir, exist_ok=True)

    files = {
        "scenario.md": course_design.get("scenario", "") or "",
        "driving_question.md": course_design.get("driving_question", "") or "",
        "question_chain.md": _question_chain_text(course_design),
        "activity.md": course_design.get("activity", "") or "",
        "experiment.md": course_design.get("experiment", "") or "",
        "course_design.md": _course_design_markdown(course_design),
    }

    for filename, content in files.items():
        path = os.path.join(gen_dir, filename)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
    return gen_dir
