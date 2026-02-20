"""
活动设计生成工具
根据驱动问题和时长生成完整的课堂活动方案
"""

import os
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROMPTS_PATH, get_llm


def load_prompt_template() -> str:
    """加载活动设计的 Prompt 模板"""
    template_path = os.path.join(PROMPTS_PATH, "activity.txt")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def get_duration_guidelines(duration: int) -> str:
    """
    根据课程时长返回时间分配建议

    Args:
        duration: 课程时长（分钟）

    Returns:
        时间分配指南字符串
    """
    if duration == 80:
        return """
- 总时长：80分钟（两节课：40+40）
- 第1节课（40分钟）：活动1 + 活动2（含产出1/2）
- 第2节课（40分钟）：活动3 + 实验 + 展示/反思（含产出3/实验记录/展示物）
- 必须包含：三个活动一一对应三个子问题
- 小组工作：建议每节课均包含小组讨论与产出"""
    if duration <= 45:
        return """
- 总时长：45分钟
- 建议分配：导入(5分钟) + 探究(15分钟) + 实践(15分钟) + 总结(10分钟)
- 必须包含：至少1个动手实践环节
- 小组工作：建议包含小组讨论（5-10分钟）
"""
    elif duration <= 90:
        return """
- 总时长：90分钟
- 建议分配：导入(10分钟) + 探究(20分钟) + 实践(30分钟) + 展示(20分钟) + 总结(10分钟)
- 必须包含：至少1个完整实验和1个展示环节
- 小组工作：必须包含小组协作环节（15-20分钟）
"""
    else:
        return f"""
- 总时长：{duration}分钟
- 建议分配：导入(10分钟) + 探究(25分钟) + 实践(40分钟) + 展示(30分钟) + 总结(15分钟)
- 必须包含：完整的探究-实践-展示流程
- 小组工作：充分的协作和讨论时间
"""


def generate_activity(
    driving_question: str,
    question_chain: list,
    grade_level: str,
    duration: int,
    context_summary: str,
    knowledge_snippets: Dict[str, Any],
    user_feedback: str = "",
    llm: ChatOpenAI = None,
) -> str:
    """
    生成课堂活动方案

    Args:
        driving_question: 驱动问题
        question_chain: 问题链
        grade_level: 目标年级
        duration: 课程时长（分钟）
        context_summary: 上下文摘要
        knowledge_snippets: 知识库片段
        llm: LLM 实例（可选）

    Returns:
        生成的活动方案文本
    """
    if llm is None:
        llm = get_llm()

    # 加载模板
    template = load_prompt_template()

    # 获取时间分配指南
    duration_guidelines = get_duration_guidelines(duration)

    # 格式化问题链（确保3个）
    question_chain = (question_chain or [])[:3]
    while len(question_chain) < 3:
        question_chain.append("（待补充子问题）")
    question_chain_str = "\n".join(
        f"{i+1}. {q}" for i, q in enumerate(question_chain)
    )

    # 格式化安全约束
    safety_constraints = knowledge_snippets.get("safety_constraints", [])
    if isinstance(safety_constraints, list):
        safety_str = "\n".join(f"- {item}" for item in safety_constraints)
    else:
        safety_str = str(safety_constraints)

    # 创建 Prompt
    prompt = ChatPromptTemplate.from_template(template)

    # 构建链
    chain = prompt | llm

    # 调用 LLM
    result = chain.invoke({
        "driving_question": driving_question,
        "question_chain": question_chain_str,
        "grade_level": grade_level,
        "duration": duration,
        "duration_guidelines": duration_guidelines,
        "context_summary": context_summary,
        "knowledge_snippets": knowledge_snippets.get("grade_rules", ""),
        "safety_constraints": safety_str,
        "user_feedback": user_feedback or "无",
    })

    return result.content


# 工具元信息
TOOL_INFO = {
    "name": "generate_activity",
    "description": "根据驱动问题和时长生成完整的课堂活动方案",
    "inputs": ["driving_question", "question_chain", "grade_level", "duration", "context_summary", "knowledge_snippets", "user_feedback"],
    "output": "activity",
    "updates_progress": "activity",
}
