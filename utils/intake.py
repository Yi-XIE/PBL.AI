from __future__ import annotations

from typing import Any, Dict


DEFAULT_LESSON_MINUTES = 40


CLASSROOM_MODE_MAP = {
    "常规教室": "normal",
    "机房": "computer_lab",
    "通识课实验室": "general_lab",
}


def normalize_intake(intake: Dict[str, Any]) -> Dict[str, Any]:
    if not intake:
        return {}
    knowledge_point = str(intake.get("knowledge_point", "")).strip()
    try:
        lesson_count = int(intake.get("lesson_count") or 1)
    except (TypeError, ValueError):
        lesson_count = 1
    age_group = str(intake.get("age_group", "")).strip()
    classroom_type = str(intake.get("classroom_type", "")).strip()
    return {
        "knowledge_point": knowledge_point,
        "lesson_count": max(1, lesson_count),
        "age_group": age_group,
        "classroom_type": classroom_type,
    }


def intake_to_constraints(intake: Dict[str, Any]) -> Dict[str, Any]:
    data = normalize_intake(intake)
    if not data:
        return {}
    lesson_count = data.get("lesson_count", 1) or 1
    duration = int(lesson_count) * DEFAULT_LESSON_MINUTES
    classroom_type = data.get("classroom_type", "")
    classroom_mode = CLASSROOM_MODE_MAP.get(classroom_type, "normal")
    return {
        "topic": data.get("knowledge_point", ""),
        "lesson_count": lesson_count,
        "duration": duration,
        "grade": data.get("age_group", ""),
        "classroom_mode": classroom_mode,
        "classroom_context": classroom_type,
    }


__all__ = ["normalize_intake", "intake_to_constraints", "DEFAULT_LESSON_MINUTES"]
