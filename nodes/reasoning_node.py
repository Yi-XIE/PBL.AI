"""
推理节点
负责解析用户输入、生成上下文摘要、匹配知识库、规划动作序列
"""

import json
import os
import re
from typing import Dict, Any, List

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state.agent_state import AgentState, KnowledgeSnippets
from config import KNOWLEDGE_BASE_PATH, get_llm
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate


def load_knowledge_base() -> Dict[str, Any]:
    """加载预置知识库"""
    with open(KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_user_input(user_input: str, state: AgentState) -> Dict[str, str]:
    """
    从用户输入中解析主题、年级、时长等信息

    Args:
        user_input: 用户原始输入
        state: 当前状态

    Returns:
        解析出的信息字典
    """
    # 如果状态中已有解析结果，直接使用
    if state.get("topic") and state.get("grade_level"):
        return {
            "topic": state["topic"],
            "grade_level": state["grade_level"],
            "duration": state["duration"],
        }

    # 否则从原始输入中提取
    topic = ""
    grade_level = "初中"  # 默认值
    duration = 45  # 默认值

    # 提取年级
    grade_patterns = [
        (r"小学[一二三四五六]年级?", "小学"),
        (r"初中[一二三]年级?", "初中"),
        (r"高中[一二三]年级?", "高中"),
        (r"小学", "小学"),
        (r"初中", "初中"),
        (r"高中", "高中"),
    ]
    for pattern, grade in grade_patterns:
        if re.search(pattern, user_input):
            grade_level = grade
            break

    # 提取时长
    duration_match = re.search(r"(\d+)\s*分钟", user_input)
    if duration_match:
        duration = int(duration_match.group(1))

    # 提取主题（更复杂的逻辑可以用 LLM）
    # 简单处理：移除年级和时长后的内容
    topic = user_input
    for pattern, _ in grade_patterns:
        topic = re.sub(pattern, "", topic)
    topic = re.sub(r"\d+\s*分钟", "", topic)
    topic = re.sub(r"设计|课程|PBL|为|的", "", topic)
    topic = topic.strip("，。！？、 ")

    return {
        "topic": topic or "AI通识教育",
        "grade_level": grade_level,
        "duration": duration,
    }


def match_knowledge_snippets(
    topic: str,
    grade_level: str,
    knowledge_base: Dict[str, Any]
) -> KnowledgeSnippets:
    """
    从知识库中匹配相关片段

    Args:
        topic: 课程主题
        grade_level: 年级
        knowledge_base: 知识库

    Returns:
        匹配的知识片段
    """
    # 匹配年级规则
    grade_rules = knowledge_base.get("grade_rules", {})
    grade_info = grade_rules.get(grade_level, {})
    if isinstance(grade_info, dict):
        grade_rules_str = f"""
年级：{grade_info.get('description', '')}
教学风格：{grade_info.get('teaching_style', '')}
时间约束：{grade_info.get('time_constraint', '')}
材料约束：{grade_info.get('material_constraint', '')}
认知水平：{grade_info.get('cognitive_level', '')}
"""
    else:
        grade_rules_str = str(grade_info)

    # 匹配主题模板
    topic_templates = knowledge_base.get("topic_templates", {})
    topic_template = ""
    best_match = None

    for template_name, template_info in topic_templates.items():
        keywords = template_info.get("keywords", [])
        for keyword in keywords:
            if keyword in topic:
                best_match = template_name
                break
        if best_match:
            break

    if best_match and best_match in topic_templates:
        info = topic_templates[best_match]
        topic_template = f"""
主题类型：{best_match}
生活场景：{', '.join(info.get('life_scenarios', []))}
类比建议：{info.get('analogy', '')}
活动建议：{', '.join(info.get('activities', []))}
"""

    # 获取安全约束
    safety_constraints = knowledge_base.get("safety_constraints", [])

    return KnowledgeSnippets(
        grade_rules=grade_rules_str,
        topic_template=topic_template,
        safety_constraints=safety_constraints,
    )


def generate_context_summary(
    topic: str,
    grade_level: str,
    duration: int,
    knowledge_snippets: KnowledgeSnippets,
    llm: ChatOpenAI = None,
) -> str:
    """
    使用 LLM 生成上下文摘要

    Args:
        topic: 课程主题
        grade_level: 年级
        duration: 时长
        knowledge_snippets: 知识片段
        llm: LLM 实例

    Returns:
        上下文摘要
    """
    if llm is None:
        llm = get_llm(temperature=0.3)

    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一位PBL课程设计专家。请根据以下信息生成一个简洁的上下文摘要。
摘要应该包含：
1. 目标学生的认知特点
2. 课程时长的约束
3. 教学重点和注意事项
4. 适合的类比或引入方式

请用2-3句话概括，每句话不超过30字。"""),
        ("user", """
课程主题：{topic}
目标年级：{grade_level}
课程时长：{duration}分钟
年级规则：{grade_rules}
主题模板：{topic_template}
""")
    ])

    chain = prompt | llm
    result = chain.invoke({
        "topic": topic,
        "grade_level": grade_level,
        "duration": duration,
        "grade_rules": knowledge_snippets["grade_rules"],
        "topic_template": knowledge_snippets["topic_template"],
    })

    return result.content.strip()


def plan_action_sequence(
    state: AgentState,
    feedback_target: str = None,
) -> List[str]:
    """
    规划动作序列

    Args:
        state: 当前状态
        feedback_target: 用户反馈的目标组件（如果有）

    Returns:
        动作序列列表
    """
    # 如果有用户反馈且指定了目标，只重新生成该组件
    if feedback_target:
        target_to_action = {
            "scenario": ["generate_scenario"],
            "driving_question": ["generate_driving_question"],
            "question_chain": ["generate_driving_question"],
            "activity": ["generate_activity"],
            "experiment": ["generate_experiment"],
        }
        return target_to_action.get(feedback_target, ["generate_scenario"])

    # 否则生成完整序列
    progress = state.get("design_progress", {})

    actions = []
    if not progress.get("scenario"):
        actions.append("generate_scenario")
    if not progress.get("driving_question"):
        actions.append("generate_driving_question")
    if not progress.get("activity"):
        actions.append("generate_activity")
    if not progress.get("experiment"):
        actions.append("generate_experiment")

    return actions


def reasoning_node(state: AgentState) -> Dict[str, Any]:
    """
    推理节点主函数

    Args:
        state: 当前状态

    Returns:
        状态更新字典
    """
    # 加载知识库
    knowledge_base = load_knowledge_base()

    # 解析用户输入
    user_input = state.get("user_input", "")
    parsed = parse_user_input(user_input, state)

    topic = parsed["topic"]
    grade_level = parsed["grade_level"]
    duration = parsed["duration"]

    # 匹配知识片段
    knowledge_snippets = match_knowledge_snippets(topic, grade_level, knowledge_base)

    # 生成上下文摘要
    context_summary = generate_context_summary(
        topic, grade_level, duration, knowledge_snippets
    )

    # 检查用户反馈
    feedback_target = state.get("feedback_target")

    # 规划动作序列
    action_sequence = plan_action_sequence(state, feedback_target)

    # 生成推理过程
    thought = f"""
分析用户请求：
- 主题：{topic}
- 年级：{grade_level}
- 时长：{duration}分钟

上下文摘要：
{context_summary}

需要生成的组件：{', '.join(action_sequence)}
"""

    return {
        "topic": topic,
        "grade_level": grade_level,
        "duration": duration,
        "context_summary": context_summary,
        "knowledge_snippets": knowledge_snippets,
        "thought": thought,
        "action_sequence": action_sequence,
        "current_action_index": 0,
        "feedback_target": None,  # 清除反馈目标
    }
