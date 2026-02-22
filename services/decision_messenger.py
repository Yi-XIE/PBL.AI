from __future__ import annotations

from typing import List

from langchain_core.prompts import ChatPromptTemplate

from adapters.llm import get_llm
from core.models import DecisionResult, Task
from core.types import StageType
from utils.intake import intake_to_constraints


def _summarize_candidates(task: Task, stage: StageType) -> str:
    artifact = task.artifacts.get(stage)
    if not artifact or not artifact.candidates:
        return ""
    lines: List[str] = []
    for cand in artifact.candidates:
        title = cand.title or ""
        snippet = ""
        content = cand.content or {}
        if isinstance(content, dict):
            for key in ("scenario", "driving_question", "question_chain", "activity", "experiment"):
                if key in content:
                    value = content.get(key)
                    if isinstance(value, list):
                        snippet = " / ".join(str(v) for v in value[:3])
                    else:
                        snippet = str(value)[:120]
                    break
        lines.append(f"{cand.id}: {title} | {snippet}")
    return "\n".join(lines)


def build_decision_message(task: Task, decision: DecisionResult) -> str:
    stage = task.current_stage
    candidates_summary = _summarize_candidates(task, stage)
    conflicts = task.conflicts.get(stage, [])
    conflict_summary = ", ".join([f"{c.severity.value}:{c.summary}" for c in conflicts]) if conflicts else ""
    constraints = {}
    if task.tool_seed:
        constraints = task.tool_seed.constraints or {}
    elif isinstance(task.entry_data, dict):
        constraints = task.entry_data.get("constraints") or intake_to_constraints(task.entry_data.get("intake") or {})

    grade = constraints.get("grade", "")
    classroom = constraints.get("classroom_context", "") or constraints.get("classroom_mode", "")

    template = (
        "You are a project-based learning co-creator assistant. Reply in short, natural Chinese or English (2-4 sentences).\n"
        "Must include: (1) current stage and next step.\n"
        "(2) If direction=backward_completion or force_exit, clearly tell the user what to do.\n"
        "(3) If candidates exist, guess the user's preferred style and ask if they want other styles.\n\n"
        "Decision:\n"
        "direction: {direction}\n"
        "next_stage: {next_stage}\n"
        "user_message: {user_message}\n"
        "summary: {summary}\n\n"
        "Classroom:\n"
        "grade: {grade}\n"
        "classroom: {classroom}\n\n"
        "stage: {stage}\n"
        "candidates:\n{candidates}\n\n"
        "conflicts:\n{conflicts}\n"
    )

    prompt = ChatPromptTemplate.from_template(template)
    payload = {
        "direction": decision.direction,
        "next_stage": decision.next_stage.value if decision.next_stage else "",
        "user_message": decision.user_message or "",
        "summary": decision.explanation.summary if decision.explanation else "",
        "grade": grade or "unknown",
        "classroom": classroom or "unknown",
        "stage": stage.value if stage else "",
        "candidates": candidates_summary or "none",
        "conflicts": conflict_summary or "none",
    }

    llm_candidates = []
    try:
        llm_candidates.append(get_llm(purpose="decision"))
    except Exception as exc:
        pass
    try:
        llm_candidates.append(get_llm())
    except Exception as exc:
        pass

    for llm in llm_candidates:
        try:
            chain = prompt | llm
            result = chain.invoke(payload)
            text = (result.content or "").strip()
            if text:
                return text
        except Exception as exc:
            pass

    direction = (decision.direction or "").lower()
    if direction in {"backward_completion", "require_previous"}:
        return "我还缺少上一阶段的确认：请先在中间选择一个候选方案，我们再继续下一步。"
    if direction in {"force_exit"}:
        return "现在还不能继续：请先按提示解决冲突或补齐必要信息，然后我再推进后续环节。"
    return "候选已准备好：请在中间选择你更喜欢的方案；也可以直接告诉我你想怎么改，我会据此再生成一轮。"


__all__ = ["build_decision_message"]
