from __future__ import annotations

from typing import List

from core.models import Conflict, ConflictOption, ToolSeed
from core.types import ConflictSeverity, StageType
from validators.base import ValidationResult


def validate_activity_alignment(
    tool_seed: ToolSeed,
    question_chain: List[str],
    activity_text: str,
) -> ValidationResult:
    warnings: List[str] = []
    missing_topic = False
    missing_chain = False
    missing_constraints = False

    constraints = tool_seed.constraints or {}
    topic = constraints.get("topic") or tool_seed.user_intent or tool_seed.tool_name

    if topic and topic not in activity_text:
        missing_topic = True
        warnings.append("Activity does not mention the topic keyword.")

    if question_chain:
        hits = [q for q in question_chain if q and q in activity_text]
        if not hits:
            # Accept explicit sub-question markers as sufficient alignment.
            marker_groups = [
                ["子问题1", "Sub-question 1", "Q1"],
                ["子问题2", "Sub-question 2", "Q2"],
                ["子问题3", "Sub-question 3", "Q3"],
            ]
            normalized = activity_text or ""
            if all(any(token in normalized for token in group) for group in marker_groups):
                hits = ["markers"]
            else:
                missing_chain = True
                warnings.append("Activity does not reflect the question chain.")

    tool_constraints = constraints.get("tool_constraints", "")
    if tool_constraints and tool_constraints not in activity_text:
        missing_constraints = True
        warnings.append("Activity does not mention tool constraints.")

    if not warnings:
        return ValidationResult()

    if missing_topic and missing_chain:
        severity = ConflictSeverity.blocking
    elif missing_topic or missing_chain:
        severity = ConflictSeverity.warning
    else:
        severity = ConflictSeverity.info

    conflict = Conflict(
        stage=StageType.activity,
        severity=severity,
        summary="Activity alignment with tool_seed/question_chain is insufficient.",
        warnings=warnings,
        conflict_options=[
            ConflictOption(
                option="A",
                title="Adjust tool_seed parameters",
                description="Modify tool_seed topic, constraints, or context to fit the activity.",
            ),
            ConflictOption(
                option="B",
                title="Select a different question chain",
                description="Choose or regenerate a question_chain that matches the activity.",
            ),
            ConflictOption(
                option="C",
                title="Generate a compromise plan",
                description="Produce a compromise plan and note the trade-offs.",
            ),
        ],
        recommendation="Align the question chain and topic first, then refine activity details.",
    )

    return ValidationResult(conflicts=[conflict])
