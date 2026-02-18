"""
执行节点
负责调用生成工具，更新课程设计和进度
"""

import os
from typing import Dict, Any

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state.agent_state import AgentState
from tools import get_tool


def action_node(state: AgentState) -> Dict[str, Any]:
    """
    执行节点主函数

    根据当前动作索引执行对应的工具，更新课程设计和进度

    Args:
        state: 当前状态

    Returns:
        状态更新字典
    """
    # 获取当前要执行的动作
    action_sequence = state.get("action_sequence", [])
    current_index = state.get("current_action_index", 0)

    if current_index >= len(action_sequence):
        # 所有动作已完成
        return {"current_action_index": current_index}

    action_name = action_sequence[current_index]
    tool_func = get_tool(action_name)

    # 准备工具输入
    course_design = state.get("course_design", {})
    knowledge_snippets = state.get("knowledge_snippets", {})

    # 根据不同的工具准备不同的输入
    if action_name == "generate_scenario":
        result = tool_func(
            topic=state["topic"],
            grade_level=state["grade_level"],
            duration=state["duration"],
            context_summary=state.get("context_summary", ""),
            knowledge_snippets=knowledge_snippets,
        )
        course_design["scenario"] = result
        progress_update = {"scenario": True}

    elif action_name == "generate_driving_question":
        result = tool_func(
            scenario=course_design.get("scenario", ""),
            grade_level=state["grade_level"],
            context_summary=state.get("context_summary", ""),
        )
        course_design["driving_question"] = result.get("driving_question", "")
        course_design["question_chain"] = result.get("question_chain", [])
        progress_update = {"driving_question": True, "question_chain": True}

    elif action_name == "generate_activity":
        result = tool_func(
            driving_question=course_design.get("driving_question", ""),
            question_chain=course_design.get("question_chain", []),
            grade_level=state["grade_level"],
            duration=state["duration"],
            context_summary=state.get("context_summary", ""),
            knowledge_snippets=knowledge_snippets,
        )
        course_design["activity"] = result
        progress_update = {"activity": True}

    elif action_name == "generate_experiment":
        # 获取活动摘要（取活动设计的前500字作为摘要）
        activity_summary = course_design.get("activity", "")[:500]

        result = tool_func(
            topic=state["topic"],
            grade_level=state["grade_level"],
            driving_question=course_design.get("driving_question", ""),
            activity_summary=activity_summary,
            context_summary=state.get("context_summary", ""),
            knowledge_snippets=knowledge_snippets,
        )
        course_design["experiment"] = result
        progress_update = {"experiment": True}

    else:
        raise ValueError(f"Unknown action: {action_name}")

    # 更新进度
    design_progress = state.get("design_progress", {})
    design_progress.update(progress_update)

    # 记录观察结果
    observations = state.get("observations", [])
    observations.append(f"[{action_name}] 完成")

    return {
        "course_design": course_design,
        "design_progress": design_progress,
        "current_action_index": current_index + 1,
        "observations": observations,
    }


def should_continue(state: AgentState) -> str:
    """
    判断是否需要继续执行

    Args:
        state: 当前状态

    Returns:
        "continue" 或 "end"
    """
    action_sequence = state.get("action_sequence", [])
    current_index = state.get("current_action_index", 0)

    if current_index < len(action_sequence):
        return "continue"
    else:
        return "end"
