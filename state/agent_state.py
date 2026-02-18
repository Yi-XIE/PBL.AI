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

    # === 课程设计区域 ===
    course_design: CourseDesign  # 包含5个组件的完整课程方案

    # === 进度追踪 ===
    design_progress: DesignProgress  # 各组件完成状态标记

    # === 智能上下文 ===
    context_summary: str    # 推理节点生成的定制化上下文摘要

    # === 规划信息 ===
    thought: str            # 推理过程
    action_sequence: List[str]  # 待执行的动作列表
    current_action_index: int   # 当前执行到的动作索引
    observations: List[str]     # 动作执行结果

    # === 知识缓存 ===
    knowledge_snippets: KnowledgeSnippets  # 从预置知识库匹配的规则片段

    # === 用户反馈 ===
    user_feedback: Optional[str]  # 用户修改意见
    feedback_target: Optional[str]  # 需要修改的组件


def create_initial_state(
    user_input: str,
    topic: str,
    grade_level: str,
    duration: int
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

        # 课程设计（初始为空）
        course_design=CourseDesign(
            scenario="",
            driving_question="",
            question_chain=[],
            activity="",
            experiment="",
        ),

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
        current_action_index=0,
        observations=[],

        # 知识缓存
        knowledge_snippets=KnowledgeSnippets(
            grade_rules="",
            topic_template="",
            safety_constraints=[],
        ),

        # 用户反馈
        user_feedback=None,
        feedback_target=None,
    )


def is_design_complete(state: AgentState) -> bool:
    """
    检查课程设计是否完成

    Args:
        state: 当前状态

    Returns:
        所有组件是否都已完成
    """
    progress = state["design_progress"]
    return all([
        progress["scenario"],
        progress["driving_question"],
        progress["question_chain"],
        progress["activity"],
        progress["experiment"],
    ])
