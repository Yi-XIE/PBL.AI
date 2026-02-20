"""
HITL Action Loop 节点
负责生成组件、等待用户确认，以及处理重生成与级联规则
"""

from typing import Dict, Any, List

from state.agent_state import AgentState, is_design_complete
from nodes.reasoning_node import plan_action_sequence, get_component_order
from nodes.action_node import generate_component


def _get_feedback(state: AgentState, component: str) -> str:
    feedback = state.get("user_feedback")
    if isinstance(feedback, dict):
        return feedback.get(component, "") or ""
    if isinstance(feedback, str):
        return feedback
    return ""


def _should_keep_downstream(feedback: str) -> bool:
    keywords = ["只改当前", "不动后面", "保留后面", "仅修改当前", "只微调"]
    return any(k in feedback for k in keywords)


def _apply_cascade_reset(
    course_design: Dict[str, Any],
    design_progress: Dict[str, bool],
    component_validity: Dict[str, str],
    locked_components: List[str],
    target: str,
    cascade: bool,
) -> None:
    order = get_component_order()
    if target not in order:
        return
    start_index = order.index(target)
    targets = order[start_index:] if cascade else [target]

    for comp in targets:
        if comp == "driving_question":
            course_design["driving_question"] = ""
            course_design["question_chain"] = []
            design_progress["driving_question"] = False
            design_progress["question_chain"] = False
            component_validity["driving_question"] = "INVALID"
            component_validity["question_chain"] = "INVALID"
        else:
            course_design[comp] = ""
            design_progress[comp] = False
            component_validity[comp] = "INVALID"
        if comp in locked_components:
            locked_components.remove(comp)


def _build_preview(component: str, course_design: Dict[str, Any]) -> Dict[str, Any]:
    if component == "scenario":
        return {"title": "场景预览", "text": course_design.get("scenario", "")}
    if component == "driving_question":
        return {
            "title": "驱动问题预览",
            "text": course_design.get("driving_question", ""),
            "question_chain": course_design.get("question_chain", []),
        }
    if component == "activity":
        return {"title": "活动预览", "text": course_design.get("activity", "")}
    if component == "experiment":
        return {"title": "实验预览", "text": course_design.get("experiment", "")}
    return {"title": "预览", "text": ""}


def _apply_candidate_selection(
    component: str,
    candidate: Dict[str, Any],
    course_design: Dict[str, Any],
    design_progress: Dict[str, bool],
    component_validity: Dict[str, str],
) -> None:
    if component != "driving_question":
        return
    course_design["driving_question"] = candidate.get("driving_question", "")
    course_design["question_chain"] = candidate.get("question_chain", [])
    design_progress["driving_question"] = True
    design_progress["question_chain"] = True
    component_validity["driving_question"] = "VALID"
    component_validity["question_chain"] = "VALID"


def hitl_loop_node(state: AgentState) -> Dict[str, Any]:
    hitl_enabled = state.get("hitl_enabled", True)

    course_design = dict(state.get("course_design", {}))
    design_progress = dict(state.get("design_progress", {}))
    component_validity = dict(state.get("component_validity", {}))
    locked_components = list(state.get("locked_components", []))
    observations = list(state.get("observations", []))
    action_inputs = list(state.get("action_inputs", []))

    pending_component = state.get("pending_component")
    pending_preview = dict(state.get("pending_preview", {}))
    pending_candidates = list(state.get("pending_candidates", []))
    selected_candidate_id = state.get("selected_candidate_id")
    await_user = state.get("await_user", False)
    user_decision = state.get("user_decision")
    feedback_target = state.get("feedback_target")

    # 如果在等待用户且未给出决策，直接返回等待状态
    if hitl_enabled and await_user and not user_decision:
        return {
            "course_design": course_design,
            "design_progress": design_progress,
            "component_validity": component_validity,
            "locked_components": locked_components,
            "observations": observations,
            "action_inputs": action_inputs,
            "await_user": True,
            "pending_component": pending_component,
            "pending_preview": pending_preview,
            "pending_candidates": pending_candidates,
            "selected_candidate_id": selected_candidate_id,
        }

    # 如果有用户决策，先应用
    if hitl_enabled and await_user and user_decision:
        current = pending_component or state.get("current_component") or ""
        if user_decision in ("accept", "select_candidate"):
            if pending_candidates and selected_candidate_id:
                selected = next(
                    (cand for cand in pending_candidates if cand.get("id") == selected_candidate_id),
                    None,
                )
                if selected:
                    _apply_candidate_selection(
                        current,
                        selected,
                        course_design,
                        design_progress,
                        component_validity,
                    )
            if current and current not in locked_components:
                locked_components.append(current)
            component_validity[current] = "VALID"
        elif user_decision == "regenerate":
            target = feedback_target or current
            feedback = _get_feedback(state, target)
            cascade = state.get("cascade_default", True)
            if cascade and _should_keep_downstream(feedback):
                cascade = False
            _apply_cascade_reset(
                course_design,
                design_progress,
                component_validity,
                locked_components,
                target,
                cascade,
            )
        await_user = False
        pending_component = None
        pending_preview = {}
        pending_candidates = []
        selected_candidate_id = None
        user_decision = None
        feedback_target = None

    # 更新动作序列
    tmp_state = dict(state)
    tmp_state["course_design"] = course_design
    tmp_state["design_progress"] = design_progress
    tmp_state["component_validity"] = component_validity
    action_sequence = plan_action_sequence(tmp_state)

    if not action_sequence or is_design_complete(tmp_state):
        return {
            "course_design": course_design,
            "design_progress": design_progress,
            "component_validity": component_validity,
            "locked_components": locked_components,
            "observations": observations,
            "action_inputs": action_inputs,
            "action_sequence": action_sequence,
            "current_component": "",
            "await_user": False,
            "pending_component": None,
            "pending_preview": {},
            "pending_candidates": [],
            "selected_candidate_id": None,
            "user_decision": None,
            "feedback_target": None,
        }

    # HITL 启用：只生成一个组件并等待用户
    if hitl_enabled:
        component = action_sequence[0]
        feedback = _get_feedback(state, component)
        gen_updates = generate_component(
            {
                **state,
                "course_design": course_design,
                "design_progress": design_progress,
                "component_validity": component_validity,
                "observations": observations,
                "action_inputs": action_inputs,
            },
            component,
            feedback,
        )
        course_design = gen_updates["course_design"]
        design_progress = gen_updates["design_progress"]
        component_validity = gen_updates["component_validity"]
        observations = gen_updates["observations"]
        action_inputs = gen_updates["action_inputs"]
        pending_candidates = gen_updates.get("pending_candidates", [])
        selected_candidate_id = gen_updates.get("selected_candidate_id")

        pending_component = component
        pending_preview = _build_preview(component, course_design)
        await_user = True

        return {
            "course_design": course_design,
            "design_progress": design_progress,
            "component_validity": component_validity,
            "locked_components": locked_components,
            "observations": observations,
            "action_inputs": action_inputs,
            "action_sequence": action_sequence,
            "current_component": component,
            "await_user": await_user,
            "pending_component": pending_component,
            "pending_preview": pending_preview,
            "pending_candidates": pending_candidates,
            "selected_candidate_id": selected_candidate_id,
            "user_decision": None,
            "feedback_target": None,
        }

    # HITL 关闭：自动生成并接受所有剩余组件
    while action_sequence:
        component = action_sequence[0]
        feedback = _get_feedback(state, component)
        gen_updates = generate_component(
            {
                **state,
                "course_design": course_design,
                "design_progress": design_progress,
                "component_validity": component_validity,
                "observations": observations,
                "action_inputs": action_inputs,
            },
            component,
            feedback,
        )
        course_design = gen_updates["course_design"]
        design_progress = gen_updates["design_progress"]
        component_validity = gen_updates["component_validity"]
        observations = gen_updates["observations"]
        action_inputs = gen_updates["action_inputs"]

        if component not in locked_components:
            locked_components.append(component)
        component_validity[component] = "VALID"

        tmp_state["course_design"] = course_design
        tmp_state["design_progress"] = design_progress
        tmp_state["component_validity"] = component_validity
        action_sequence = plan_action_sequence(tmp_state)

    return {
        "course_design": course_design,
        "design_progress": design_progress,
        "component_validity": component_validity,
        "locked_components": locked_components,
        "observations": observations,
        "action_inputs": action_inputs,
        "action_sequence": action_sequence,
        "current_component": "",
        "await_user": False,
        "pending_component": None,
        "pending_preview": {},
        "pending_candidates": [],
        "selected_candidate_id": None,
        "user_decision": None,
        "feedback_target": None,
    }
