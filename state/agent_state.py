"""
AgentState 定义
LangGraph 工作流的全局状态管理
"""

from typing import TypedDict, Optional, Dict, List, Any


class CourseDesign(TypedDict):
    """课程设计方案"""
    scenario: str           # 教学场景
    driving_question: str   # 驱动问题
    question_chain: List[str]  # 问题链
    activity: str           # 活动设计
    experiment: str         # 实验设计


class DesignProgress(TypedDict):
    """各组件完成状态"""
    scenario: bool
    driving_question: bool
    question_chain: bool
    activity: bool
    experiment: bool


class KnowledgeSnippets(TypedDict):
    """知识库片段"""
    grade_rules: str        # 年级规则
    topic_template: str     # 主题模板
    safety_constraints: List[str]  # 安全约束


class AgentState(TypedDict):
    """
    Agent 全局状态

    包含用户输入、课程设计、进度追踪、智能上下文、规划信息和知识缓存
    """

    # === 用户输入区域 ===
    user_input: str         # 原始请求
    topic: str              # 课程主题
    grade_level: str        # 年级（小学/初中/高中）
    duration: int           # 课时（分钟）
    classroom_context: str  # 课堂条件描述
    classroom_mode: str     # normal | no_device | computer_lab

    # === 起点与组件输入 ===
    start_from: str                 # topic | scenario | activity | experiment
    provided_components: Dict[str, Any]  # 用户提供的已有组件内容

    # === 课程设计区域 ===
    course_design: CourseDesign  # 包含5个组件的完整课程方案
    locked_components: List[str]  # 已确认（accepted）的组件
    component_validity: Dict[str, str]  # VALID / INVALID / EMPTY

    # === 进度追踪 ===
    design_progress: DesignProgress  # 各组件完成状态标记

    # === 智能上下文 ===
    context_summary: str    # 推理节点生成的定制化上下文摘要

    # === 规划信息 ===
    thought: str            # 推理过程
    action_sequence: List[str]  # 待执行的动作列表
    action_inputs: List[Dict[str, Any]]  # 每个动作的输入快照（用于审计/回放）
    current_action_index: int   # 当前执行到的动作索引
    observations: List[str]     # 动作执行结果
    current_component: str      # 当前组件

    # === 知识缓存 ===
    knowledge_snippets: KnowledgeSnippets  # 从预置知识库匹配的规则片段

    # === 用户反馈 ===
    user_feedback: Optional[Dict[str, str]]  # 用户修改意见（按组件）
    feedback_target: Optional[str]  # 需要修改的组件
    user_decision: Optional[str]    # accept / regenerate

    # === HITL 控制 ===
    await_user: bool               # 是否等待用户确认
    pending_component: Optional[str]  # 待确认组件
    pending_preview: Dict[str, Any]   # 待确认预览内容
    hitl_enabled: bool             # 是否启用 HITL
    cascade_default: bool          # 是否默认级联重生成
    interactive: bool              # 是否交互模式


def create_initial_state(
    user_input: str,
    topic: str,
    grade_level: str,
    duration: int,
    classroom_context: str = "",
    classroom_mode: str = "normal",
    start_from: str = "topic",
    provided_components: Optional[Dict[str, Any]] = None,
    hitl_enabled: bool = True,
    cascade_default: bool = True,
    interactive: bool = False,
) -> AgentState:
    """
    创建初始状态

    Args:
        user_input: 用户原始输入
        topic: 课程主题
        grade_level: 年级
        duration: 课时（分钟）

    Returns:
        初始化的 AgentState
    """
    return AgentState(
        # 用户输入
        user_input=user_input,
        topic=topic,
        grade_level=grade_level,
        duration=duration,
        classroom_context=classroom_context,
        classroom_mode=classroom_mode,
        start_from=start_from,
        provided_components=provided_components or {},

        # 课程设计（初始为空）
        course_design=CourseDesign(
            scenario="",
            driving_question="",
            question_chain=[],
            activity="",
            experiment="",
        ),
        locked_components=[],
        component_validity={
            "scenario": "EMPTY",
            "driving_question": "EMPTY",
            "question_chain": "EMPTY",
            "activity": "EMPTY",
            "experiment": "EMPTY",
        },

        # 进度追踪（初始全部未完成）
        design_progress=DesignProgress(
            scenario=False,
            driving_question=False,
            question_chain=False,
            activity=False,
            experiment=False,
        ),

        # 智能上下文
        context_summary="",

        # 规划信息
        thought="",
        action_sequence=[],
        action_inputs=[],
        current_action_index=0,
        observations=[],
        current_component="",

        # 知识缓存
        knowledge_snippets=KnowledgeSnippets(
            grade_rules="",
            topic_template="",
            safety_constraints=[],
        ),

        # 用户反馈
        user_feedback=None,
        feedback_target=None,
        user_decision=None,

        # HITL
        await_user=False,
        pending_component=None,
        pending_preview={},
        hitl_enabled=hitl_enabled,
        cascade_default=cascade_default,
        interactive=interactive,
    )


def is_design_complete(state: AgentState) -> bool:
    """
    检查课程设计是否完成

    Args:
        state: 当前状态

    Returns:
        所有组件是否都已完成
    """
    start_from = state.get("start_from", "topic")
    progress = state["design_progress"]

    if start_from in ("topic", "scenario"):
        required = ["scenario", "driving_question", "question_chain", "activity", "experiment"]
    elif start_from == "activity":
        required = ["activity", "experiment"]
    elif start_from == "experiment":
        required = ["experiment"]
    else:
        required = ["scenario", "driving_question", "question_chain", "activity", "experiment"]

    return all(progress.get(k, False) for k in required)
