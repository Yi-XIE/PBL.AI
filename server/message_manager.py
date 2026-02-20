from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from server.task_manager import stage_label, stage_progress


def _new_message(msg_type: str, message: str, stage: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": uuid4().hex,
        "type": msg_type,
        "message": message,
        "stage": stage,
        "created_at": time.time(),
    }


def _dedup(messages: List[Dict[str, Any]], candidate: Dict[str, Any]) -> bool:
    if not messages:
        return True
    last = messages[-1]
    if last.get("type") == candidate.get("type") and last.get("message") == candidate.get("message"):
        return False
    return True


def build_status_message(task: Dict[str, Any], state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    stage = task.get("current_stage", "")
    progress = stage_progress(task, stage)
    if task.get("status") == "completed":
        return _new_message("status", "任务已完成，可在左侧查看课程总览。")
    if not stage:
        return _new_message("status", "正在准备下一步。")
    label = stage_label(stage)
    if state.get("await_user"):
        suffix = f"（第 {progress} 步）" if progress else ""
        return _new_message("status", f"已生成{label}{suffix}，等待你的确认。", stage)
    suffix = f"（第 {progress} 步）" if progress else ""
    return _new_message("status", f"正在生成{label}{suffix}。", stage)


def build_knowledge_message(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    snippets = state.get("knowledge_snippets") or {}
    if not snippets:
        return None
    return _new_message("status", "本步骤参考了知识模板与课程标准要求。")


def build_decision_messages(decision: Dict[str, str]) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = []
    explanation = decision.get("explanation", "").strip()
    user_message = decision.get("user_message", "").strip()
    if explanation:
        messages.append(_new_message("explanation", explanation))
    if user_message:
        messages.append(_new_message("action", user_message))
    return messages


def append_messages(messages: List[Dict[str, Any]], additions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for msg in additions:
        if _dedup(messages, msg):
            messages.append(msg)
    return messages
