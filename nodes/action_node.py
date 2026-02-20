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
from config import MULTI_OPTION_COUNT
from tools.generate_driving_question import generate_driving_question_candidates


def generate_component(
    state: AgentState,
    component: str,
    user_feedback: str = "",
) -> Dict[str, Any]:
    """
    生成指定组件并更新状态
    """
    component_to_tool = {
        "scenario": "generate_scenario",
        "driving_question": "generate_driving_question",
        "activity": "generate_activity",
        "experiment": "generate_experiment",
    }
    tool_name = component_to_tool.get(component)
    if not tool_name:
        raise ValueError(f"Unknown component: {component}")

    tool_func = get_tool(tool_name)

    course_design = state.get("course_design", {})
    knowledge_snippets = state.get("knowledge_snippets", {})

    if component == "scenario":
        state["pending_candidates"] = []
        state["selected_candidate_id"] = None
        result = tool_func(
            topic=state["topic"],
            grade_level=state["grade_level"],
            duration=state["duration"],
            context_summary=state.get("context_summary", ""),
            knowledge_snippets=knowledge_snippets,
            user_feedback=user_feedback,
        )
        course_design["scenario"] = result
        progress_update = {"scenario": True}

    elif component == "driving_question":
        if state.get("multi_option", True):
            candidates = generate_driving_question_candidates(
                scenario=course_design.get("scenario", ""),
                grade_level=state["grade_level"],
                context_summary=state.get("context_summary", ""),
                user_feedback=user_feedback,
                count=max(1, MULTI_OPTION_COUNT),
            )
            selected = candidates[0] if candidates else {}
            course_design["driving_question"] = selected.get("driving_question", "")
            course_design["question_chain"] = selected.get("question_chain", [])
            state["pending_candidates"] = candidates
            state["selected_candidate_id"] = selected.get("id")
        else:
            result = tool_func(
                scenario=course_design.get("scenario", ""),
                grade_level=state["grade_level"],
                context_summary=state.get("context_summary", ""),
                user_feedback=user_feedback,
            )
            course_design["driving_question"] = result.get("driving_question", "")
            course_design["question_chain"] = result.get("question_chain", [])
            state["pending_candidates"] = []
            state["selected_candidate_id"] = None
        progress_update = {"driving_question": True, "question_chain": True}

    elif component == "activity":
        state["pending_candidates"] = []
        state["selected_candidate_id"] = None
        result = tool_func(
            driving_question=course_design.get("driving_question", ""),
            question_chain=course_design.get("question_chain", []),
            grade_level=state["grade_level"],
            duration=state["duration"],
            context_summary=state.get("context_summary", ""),
            knowledge_snippets=knowledge_snippets,
            user_feedback=user_feedback,
        )
        course_design["activity"] = result
        progress_update = {"activity": True}

    elif component == "experiment":
        state["pending_candidates"] = []
        state["selected_candidate_id"] = None
        activity_summary = course_design.get("activity", "")[:500]
        result = tool_func(
            topic=state["topic"],
            grade_level=state["grade_level"],
            driving_question=course_design.get("driving_question", ""),
            activity_summary=activity_summary,
            context_summary=state.get("context_summary", ""),
            knowledge_snippets=knowledge_snippets,
            classroom_mode=state.get("classroom_mode", "normal"),
            classroom_context=state.get("classroom_context", ""),
            user_feedback=user_feedback,
        )
        course_design["experiment"] = result
        progress_update = {"experiment": True}

    else:
        raise ValueError(f"Unknown component: {component}")

    design_progress = state.get("design_progress", {})
    design_progress.update(progress_update)

    component_validity = state.get("component_validity", {})
    if component == "driving_question":
        component_validity["driving_question"] = "VALID"
        component_validity["question_chain"] = "VALID"
    else:
        component_validity[component] = "VALID"

    observations = state.get("observations", [])
    observations.append(f"[{tool_name}] 完成")

    action_inputs = state.get("action_inputs", [])
    action_inputs.append({
        "action": tool_name,
        "component": component,
        "inputs": {
            "topic": state.get("topic"),
            "grade_level": state.get("grade_level"),
            "duration": state.get("duration"),
            "context_summary": state.get("context_summary", ""),
            "knowledge_snippets": knowledge_snippets,
            "course_design_snapshot": {
                "scenario": course_design.get("scenario", ""),
                "driving_question": course_design.get("driving_question", ""),
                "question_chain": course_design.get("question_chain", []),
                "activity": course_design.get("activity", ""),
                "experiment": course_design.get("experiment", ""),
            },
            "user_feedback": user_feedback,
        },
    })

    return {
        "course_design": course_design,
        "design_progress": design_progress,
        "component_validity": component_validity,
        "observations": observations,
        "action_inputs": action_inputs,
        "pending_candidates": state.get("pending_candidates", []),
        "selected_candidate_id": state.get("selected_candidate_id"),
    }


def action_node(state: AgentState) -> Dict[str, Any]:
    """
    执行节点主函数

    根据当前动作索引执行对应的组件生成，更新课程设计和进度
    """
    action_sequence = state.get("action_sequence", [])
    current_index = state.get("current_action_index", 0)

    if current_index >= len(action_sequence):
        return {"current_action_index": current_index}

    component = action_sequence[current_index]
    feedback_target = state.get("feedback_target")
    user_feedback = ""
    if feedback_target and feedback_target == component:
        feedback = state.get("user_feedback")
        if isinstance(feedback, dict):
            user_feedback = feedback.get(component, "") or ""
        else:
            user_feedback = feedback or ""

    updates = generate_component(state, component, user_feedback)
    updates["current_action_index"] = current_index + 1
    updates["user_feedback"] = None if user_feedback else state.get("user_feedback")
    updates["feedback_target"] = None if user_feedback else state.get("feedback_target")
    return updates


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
