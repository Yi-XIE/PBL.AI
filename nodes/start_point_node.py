"""
起点判定节点
负责校验 start_from 与已有组件内容，并处理回退逻辑
"""

from typing import Dict, Any

from state.agent_state import AgentState


def _has_content(state: AgentState, component: str) -> bool:
    provided = state.get("provided_components", {}) or {}
    course_design = state.get("course_design", {}) or {}
    if provided.get(component):
        return True
    if course_design.get(component):
        return True
    return False


def start_point_node(state: AgentState) -> Dict[str, Any]:
    start_from = state.get("start_from") or "topic"
    provided = state.get("provided_components", {}) or {}
    course_design = state.get("course_design", {}) or {}
    observations = state.get("observations", [])

    # 同步已有组件到 provided_components（兼容旧流程直接写入 course_design 的情况）
    for key in ("scenario", "activity", "experiment", "driving_question"):
        if key not in provided and course_design.get(key):
            provided[key] = course_design.get(key)

    # 起点校验：activity/experiment 必须有内容，否则回退
    if start_from in ("activity", "experiment") and not _has_content(state, start_from):
        observations.append(f"[start_point] {start_from} 缺少内容，已回退为 topic")
        start_from = "topic"

    return {
        "start_from": start_from,
        "provided_components": provided,
        "observations": observations,
    }
