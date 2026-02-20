from __future__ import annotations

import time
from typing import Any, Dict, List

from state.agent_state import AgentState, is_design_complete


STAGE_LABELS: Dict[str, str] = {
    "scenario": "课程情境设计",
    "driving_question": "驱动问题设计",
    "question_chain": "问题链构建",
    "activity": "学习活动设计",
    "experiment": "探究与实验设计",
}


def _required_stages(start_from: str) -> List[str]:
    if start_from == "experiment":
        return ["experiment"]
    if start_from == "activity":
        return ["activity", "experiment"]
    return ["scenario", "driving_question", "question_chain", "activity", "experiment"]


def stage_label(stage: str) -> str:
    return STAGE_LABELS.get(stage, stage or "当前阶段")


def stage_progress(task: Dict[str, Any], stage: str) -> str:
    stages = task.get("stages", [])
    if stage not in stages:
        return ""
    index = stages.index(stage) + 1
    return f"{index} / {len(stages)}"


def create_task(session_id: str, state: AgentState) -> Dict[str, Any]:
    start_from = state.get("start_from", "topic")
    stages = _required_stages(start_from)
    return {
        "task_id": f"task_{session_id[:8]}",
        "session_id": session_id,
        "topic": state.get("topic", ""),
        "stages": stages,
        "current_stage": "",
        "completed_stages": [],
        "status": "active",
        "created_at": time.time(),
    }


def refresh_task(task: Dict[str, Any], state: AgentState) -> Dict[str, Any]:
    start_from = state.get("start_from", "topic")
    stages = _required_stages(start_from)
    progress = state.get("design_progress", {}) or {}
    completed = [stage for stage in stages if progress.get(stage)]

    current = ""
    if state.get("await_user") and state.get("pending_component"):
        current = state.get("pending_component") or ""
    else:
        for stage in stages:
            if not progress.get(stage):
                current = stage
                break

    status = "completed" if is_design_complete(state) else "active"
    updated = dict(task)
    updated["topic"] = state.get("topic", updated.get("topic", ""))
    updated["stages"] = stages
    updated["current_stage"] = current
    updated["completed_stages"] = completed
    updated["status"] = status
    return updated
