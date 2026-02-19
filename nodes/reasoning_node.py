"""
推理节点
负责解析用户输入、生成上下文摘要、匹配知识库、规划动作序列
"""

import json
import os
import re
from typing import Dict, Any, List, Tuple

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
    duration = 80  # 默认值（两节课 40+40）

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
    # 两节课 40+40 或 2节课
    if re.search(r"40\s*\+\s*40", user_input) or re.search(r"两节课|2节课|两节|2节", user_input):
        duration = 80

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
    anchor_type: str = "",
    anchor_content: str = "",
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

如果提供了“已有组件锚点”，请在摘要中体现与之对齐的教学取向或情境线索。
请用2-3句话概括，每句话不超过30字。"""),
        ("user", """
课程主题：{topic}
目标年级：{grade_level}
课程时长：{duration}分钟
年级规则：{grade_rules}
主题模板：{topic_template}
已有组件类型：{anchor_type}
已有组件内容：{anchor_content}
""")
    ])

    chain = prompt | llm
    result = chain.invoke({
        "topic": topic,
        "grade_level": grade_level,
        "duration": duration,
        "grade_rules": knowledge_snippets["grade_rules"],
        "topic_template": knowledge_snippets["topic_template"],
        "anchor_type": anchor_type or "无",
        "anchor_content": (anchor_content[:800] if anchor_content else "无"),
    })

    return result.content.strip()


def get_component_order() -> List[str]:
    return ["scenario", "driving_question", "activity", "experiment"]


def _start_index(start_from: str) -> int:
    if start_from in ("topic", "scenario"):
        return 0
    if start_from == "activity":
        return 2
    if start_from == "experiment":
        return 3
    return 0


def plan_action_sequence(state: AgentState) -> List[str]:
    """
    规划动作序列（基于组件）

    Args:
        state: 当前状态

    Returns:
        动作序列列表（组件名）
    """
    progress = state.get("design_progress", {})
    validity = state.get("component_validity", {})
    start_from = state.get("start_from", "topic")

    components = get_component_order()[_start_index(start_from):]
    actions: List[str] = []
    for comp in components:
        if validity.get(comp) == "INVALID":
            actions.append(comp)
            continue
        if not progress.get(comp, False):
            actions.append(comp)
    return actions


def merge_provided_components(state: AgentState) -> Tuple[Dict[str, Any], Dict[str, bool]]:
    """
    将用户提供的组件写入 course_design，并更新进度
    """
    provided = state.get("provided_components", {}) or {}
    course_design = state.get("course_design", {})
    progress = state.get("design_progress", {})
    validity = state.get("component_validity", {})
    locked = state.get("locked_components", [])

    for key, value in provided.items():
        if key in course_design and value:
            course_design[key] = value
            if key == "driving_question" and isinstance(value, dict):
                course_design["driving_question"] = value.get("driving_question", "")
                course_design["question_chain"] = value.get("question_chain", [])
                progress["driving_question"] = bool(course_design["driving_question"])
                progress["question_chain"] = bool(course_design["question_chain"])
                validity["driving_question"] = "VALID" if progress["driving_question"] else "EMPTY"
                validity["question_chain"] = "VALID" if progress["question_chain"] else "EMPTY"
            else:
                progress[key] = True
                validity[key] = "VALID"
            if key not in locked:
                locked.append(key)

    return course_design, progress


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

    # 合并用户提供的已有组件内容
    course_design = state.get("course_design", {})
    design_progress = state.get("design_progress", {})
    component_validity = state.get("component_validity", {})
    locked_components = state.get("locked_components", [])

    course_design, design_progress = merge_provided_components(state)

    # 收集已有组件作为锚点（支持任意起点）
    anchor_type = ""
    anchor_content = ""
    if course_design.get("scenario"):
        anchor_type = "场景"
        anchor_content = course_design.get("scenario", "")
    elif course_design.get("activity"):
        anchor_type = "活动"
        anchor_content = course_design.get("activity", "")
    elif course_design.get("experiment"):
        anchor_type = "实验"
        anchor_content = course_design.get("experiment", "")
    elif course_design.get("driving_question"):
        anchor_type = "驱动问题"
        anchor_content = course_design.get("driving_question", "")

    # 生成上下文摘要
    context_summary = generate_context_summary(
        topic, grade_level, duration, knowledge_snippets, anchor_type, anchor_content
    )

    # 规划动作序列
    action_sequence = plan_action_sequence(state)

    # 生成推理过程
    thought = f"""
分析用户请求：
- 主题：{topic}
- 年级：{grade_level}
- 时长：{duration}分钟
 - 起点：{state.get('start_from', 'topic')}

上下文摘要：
{context_summary}

需要生成的组件：{', '.join(action_sequence)}
"""

    # 计算当前组件
    if state.get("await_user") and state.get("pending_component"):
        current_component = state.get("pending_component") or ""
    else:
        current_component = action_sequence[0] if action_sequence else ""

    return {
        "topic": topic,
        "grade_level": grade_level,
        "duration": duration,
        "context_summary": context_summary,
        "knowledge_snippets": knowledge_snippets,
        "thought": thought,
        "action_sequence": action_sequence,
        "action_inputs": state.get("action_inputs", []),
        "current_action_index": 0,
        "course_design": course_design,
        "design_progress": design_progress,
        "component_validity": component_validity,
        "locked_components": locked_components,
        "current_component": current_component,
    }
