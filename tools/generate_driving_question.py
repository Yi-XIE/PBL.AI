"""
驱动问题生成工具
根据教学场景生成驱动问题和问题链
"""

import os
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROMPTS_PATH, get_llm


def load_prompt_template() -> str:
    """加载驱动问题的 Prompt 模板"""
    template_path = os.path.join(PROMPTS_PATH, "driving_question.txt")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def parse_question_chain(response_text: str) -> List[str]:
    """
    从响应文本中解析问题链

    Args:
        response_text: LLM 返回的文本

    Returns:
        问题链列表
    """
    questions = []
    lines = response_text.split("\n")

    in_question_chain = False
    for line in lines:
        line = line.strip()

        # 检测问题链部分开始
        if "问题链" in line or "### 问题链" in line:
            in_question_chain = True
            continue

        # 检测下一个部分开始（问题链结束）
        if in_question_chain and line.startswith("###") and "问题链" not in line:
            in_question_chain = False

        # 提取编号的问题
        if in_question_chain and line:
            # 匹配 "1. "、"1、" 等格式
            import re
            match = re.match(r"^\d+[.、]\s*(.+)", line)
            if match:
                questions.append(match.group(1).strip())

    return questions


def generate_driving_question(
    scenario: str,
    grade_level: str,
    context_summary: str,
    user_feedback: str = "",
    llm: ChatOpenAI = None,
) -> Dict[str, Any]:
    """
    生成驱动问题和问题链

    Args:
        scenario: 教学场景
        grade_level: 目标年级
        context_summary: 上下文摘要
        llm: LLM 实例（可选）

    Returns:
        包含 driving_question 和 question_chain 的字典
    """
    if llm is None:
        llm = get_llm()

    # 加载模板
    template = load_prompt_template()

    # 创建 Prompt
    prompt = ChatPromptTemplate.from_template(template)

    # 构建链
    chain = prompt | llm

    # 调用 LLM
    result = chain.invoke({
        "scenario": scenario,
        "grade_level": grade_level,
        "context_summary": context_summary,
        "user_feedback": user_feedback or "无",
    })

    response_text = result.content

    # 解析驱动问题
    driving_question = ""
    lines = response_text.split("\n")
    for i, line in enumerate(lines):
        if "驱动问题" in line and "###" in line:
            # 获取下一行作为驱动问题
            if i + 1 < len(lines):
                driving_question = lines[i + 1].strip()
                # 去除可能的方括号
                driving_question = driving_question.strip("[]")
            break

    # 解析问题链
    question_chain = parse_question_chain(response_text)
    if len(question_chain) < 3:
        # Retry once with explicit constraint
        retry_feedback = (user_feedback + "；" if user_feedback else "") + "问题链必须恰好3个子问题，不多不少。"
        result = chain.invoke({
            "scenario": scenario,
            "grade_level": grade_level,
            "context_summary": context_summary,
            "user_feedback": retry_feedback,
        })
        response_text = result.content
        question_chain = parse_question_chain(response_text)

    # Hard constraint: keep exactly 3
    if len(question_chain) >= 3:
        question_chain = question_chain[:3]
    else:
        # Pad with placeholders if still insufficient
        while len(question_chain) < 3:
            question_chain.append("（待补充：请生成一个可探究的子问题）")

    return {
        "driving_question": driving_question,
        "question_chain": question_chain,
        "raw_response": response_text,
    }


# 工具元信息
TOOL_INFO = {
    "name": "generate_driving_question",
    "description": "根据教学场景生成驱动问题和问题链",
    "inputs": ["scenario", "grade_level", "context_summary", "user_feedback"],
    "output": ["driving_question", "question_chain"],
    "updates_progress": ["driving_question", "question_chain"],
}
