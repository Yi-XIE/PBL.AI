"""
实验设计生成工具
根据主题和活动背景生成动手实验方案
"""

import os
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROMPTS_PATH, get_llm


def load_prompt_template() -> str:
    """加载实验设计的 Prompt 模板"""
    template_path = os.path.join(PROMPTS_PATH, "experiment.txt")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def generate_experiment(
    topic: str,
    grade_level: str,
    driving_question: str,
    activity_summary: str,
    context_summary: str,
    knowledge_snippets: Dict[str, Any],
    llm: ChatOpenAI = None,
) -> str:
    """
    生成动手实验方案

    Args:
        topic: 课程主题
        grade_level: 目标年级
        driving_question: 驱动问题
        activity_summary: 活动摘要
        context_summary: 上下文摘要
        knowledge_snippets: 知识库片段
        llm: LLM 实例（可选）

    Returns:
        生成的实验方案文本
    """
    if llm is None:
        llm = get_llm()

    # 加载模板
    template = load_prompt_template()

    # 格式化安全约束
    safety_constraints = knowledge_snippets.get("safety_constraints", [])
    if isinstance(safety_constraints, list):
        safety_str = "\n".join(f"- {item}" for item in safety_constraints)
    else:
        safety_str = str(safety_constraints)

    # 提取年级规则
    grade_rules = knowledge_snippets.get("grade_rules", "")

    # 创建 Prompt
    prompt = ChatPromptTemplate.from_template(template)

    # 构建链
    chain = prompt | llm

    # 调用 LLM
    result = chain.invoke({
        "topic": topic,
        "grade_level": grade_level,
        "driving_question": driving_question,
        "activity_summary": activity_summary,
        "context_summary": context_summary,
        "knowledge_snippets": grade_rules,
        "safety_constraints": safety_str,
    })

    return result.content


# 工具元信息
TOOL_INFO = {
    "name": "generate_experiment",
    "description": "根据主题和活动背景生成安全、有趣的动手实验方案",
    "inputs": ["topic", "grade_level", "driving_question", "activity_summary", "context_summary", "knowledge_snippets"],
    "output": "experiment",
    "updates_progress": "experiment",
}
