from __future__ import annotations

from typing import List

from langchain_core.prompts import ChatPromptTemplate

from adapters.llm import LLMInvocationError, get_llm
from core.models import DecisionResult, Task
from core.types import StageType


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
    llm = get_llm()
    stage = task.current_stage
    candidates_summary = _summarize_candidates(task, stage)
    conflicts = task.conflicts.get(stage, [])
    conflict_summary = ", ".join([f"{c.severity.value}:{c.summary}" for c in conflicts]) if conflicts else ""

    template = (
        "你是课程设计助手。请根据当前决策生成一段给用户的简短对话消息。\n"
        "要求：\n"
        "1) 语气简洁自然，中文输出。\n"
        "2) 如果有候选方案，请引导用户选择或给反馈。\n"
        "3) 若 direction=backward_completion，说明需要先完成的阶段。\n"
        "4) 若 direction=forward 且 next_stage 存在，说明准备进入该阶段。\n"
        "5) 不要输出 JSON，只输出一到两句对话消息。\n\n"
        "决策信息：\n"
        "direction: {direction}\n"
        "next_stage: {next_stage}\n"
        "user_message: {user_message}\n"
        "summary: {summary}\n\n"
        "当前阶段: {stage}\n"
        "候选摘要:\n{candidates}\n\n"
        "冲突摘要:\n{conflicts}\n"
    )

    prompt = ChatPromptTemplate.from_template(template)
    try:
        chain = prompt | llm
        result = chain.invoke(
            {
                "direction": decision.direction,
                "next_stage": decision.next_stage.value if decision.next_stage else "",
                "user_message": decision.user_message or "",
                "summary": decision.explanation.summary if decision.explanation else "",
                "stage": stage.value if stage else "",
                "candidates": candidates_summary or "none",
                "conflicts": conflict_summary or "none",
            }
        )
    except Exception as exc:
        raise LLMInvocationError("LLM invocation failed for decision message") from exc
    return (result.content or "").strip()


__all__ = ["build_decision_message"]
