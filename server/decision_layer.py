from __future__ import annotations

import json
import re
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate

from config import DECISION_USE_LLM, get_llm
from server.task_manager import stage_label


def _parse_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        return {}
    return {}


def _derive_stage_status(task: Dict[str, Any], state: Dict[str, Any]) -> str:
    stage = task.get("current_stage", "")
    if task.get("status") == "completed":
        return "completed"
    if state.get("await_user"):
        return "pending"
    if not stage:
        return "empty"
    validity = (state.get("component_validity") or {}).get(stage)
    if validity == "INVALID":
        return "invalid"
    if validity == "EMPTY":
        return "empty"
    if validity == "VALID":
        return "completed"
    progress = (state.get("design_progress") or {}).get(stage)
    return "completed" if progress else "in_progress"


def _fallback_decision(task: Dict[str, Any], state: Dict[str, Any], user_action: str) -> Dict[str, str]:
    current_stage = task.get("current_stage", "")
    label = stage_label(current_stage)
    if task.get("status") == "completed":
        return {
            "next_stage": "",
            "explanation": "所有阶段已经完成，可以导出课程方案。",
            "user_message": "任务已完成，如需调整请在左侧编辑对应内容。",
        }
    if state.get("await_user") and current_stage:
        return {
            "next_stage": current_stage,
            "explanation": f"{label}已生成，等待你的确认。",
            "user_message": "你可以直接确认，或输入修改意见让我重新生成。",
        }
    if current_stage:
        return {
            "next_stage": current_stage,
            "explanation": "上一阶段已经完成，需要继续推进下一步。",
            "user_message": f"下一步我会生成{label}，完成后你可以确认或提出修改。",
        }
    return {
        "next_stage": "",
        "explanation": "正在准备下一步。",
        "user_message": "如需调整，请告诉我你的想法。",
    }


def decide_next(task: Dict[str, Any], state: Dict[str, Any], user_action: str) -> Dict[str, str]:
    fallback = _fallback_decision(task, state, user_action)
    if not DECISION_USE_LLM:
        return fallback

    try:
        llm = get_llm(temperature=0.2)
        stage_status = _derive_stage_status(task, state)
        component_validity = state.get("component_validity", {})
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是课程设计助手的决策层，只做阶段决策与解释，不生成内容。"
                    "请基于输入返回 JSON："
                    "{\"next_stage\":\"\", \"explanation\":\"\", \"user_message\":\"\"}。",
                ),
                (
                    "user",
                    "Task: {task}\n"
                    "Current stage: {current_stage}\n"
                    "Stage status: {stage_status}\n"
                    "Completed stages: {completed_stages}\n"
                    "Component validity: {component_validity}\n"
                    "User action: {user_action}\n"
                    "Await user: {await_user}\n",
                ),
            ]
        )
        response = (prompt | llm).invoke(
            {
                "task": json.dumps(task, ensure_ascii=False),
                "current_stage": task.get("current_stage", ""),
                "stage_status": stage_status,
                "completed_stages": ",".join(task.get("completed_stages", [])),
                "component_validity": json.dumps(component_validity, ensure_ascii=False),
                "user_action": user_action,
                "await_user": str(state.get("await_user", False)),
            }
        )
        payload = _parse_json(response.content or "")
        if not payload:
            return fallback
        next_stage = str(payload.get("next_stage", "")).strip()
        explanation = str(payload.get("explanation", "")).strip()
        user_message = str(payload.get("user_message", "")).strip()
        if not explanation or not user_message:
            return fallback
        return {
            "next_stage": next_stage,
            "explanation": explanation,
            "user_message": user_message,
        }
    except Exception:
        return fallback
