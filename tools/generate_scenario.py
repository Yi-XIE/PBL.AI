"""
场景生成工具
根据主题、年级和上下文生成教学场景
"""

import os
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROMPTS_PATH, get_llm


def load_prompt_template() -> str:
    """加载场景生成的 Prompt 模板"""
    template_path = os.path.join(PROMPTS_PATH, "scenario.txt")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def generate_scenario(
    topic: str,
    grade_level: str,
    duration: int,
    context_summary: str,
    knowledge_snippets: Dict[str, Any],
    user_feedback: str = "",
    llm: ChatOpenAI = None,
) -> str:
    """
    生成教学场景

    Args:
        topic: 课程主题
        grade_level: 目标年级
        duration: 课程时长（分钟）
        context_summary: 上下文摘要
        knowledge_snippets: 知识库片段
        llm: LLM 实例（可选，默认使用配置的 DeepSeek）

    Returns:
        生成的教学场景文本
    """
    if llm is None:
        llm = get_llm()

    # 加载模板
    template = load_prompt_template()

    # 提取知识库信息
    grade_rules = knowledge_snippets.get("grade_rules", "")
    topic_template = knowledge_snippets.get("topic_template", "")

    # 创建 Prompt
    prompt = ChatPromptTemplate.from_template(template)

    # 构建链
    chain = prompt | llm

    # 调用 LLM
    result = chain.invoke({
        "topic": topic,
        "grade_level": grade_level,
        "duration": duration,
        "context_summary": context_summary,
        "grade_rules": grade_rules,
        "topic_template": topic_template,
        "user_feedback": user_feedback or "无",
    })

    return result.content


def parse_scenario_title(response_text: str) -> str:
    """
    浠庡搷搴旀枃鏈腑瑙ｆ瀽鍦烘櫙鍚嶇О
    """
    if not response_text:
        return ""
    lines = [line.strip() for line in response_text.splitlines()]
    for i, line in enumerate(lines):
        if line.startswith("###") and "鍦烘櫙鍚嶇О" in line:
            for j in range(i + 1, len(lines)):
                candidate = lines[j].strip()
                if candidate:
                    return candidate.strip("[]")
    for line in lines:
        if line and not line.startswith("#"):
            return line.strip("[]")
    return ""


def generate_scenario_candidates(
    topic: str,
    grade_level: str,
    duration: int,
    context_summary: str,
    knowledge_snippets: Dict[str, Any],
    user_feedback: str = "",
    count: int = 3,
    llm: ChatOpenAI = None,
) -> List[Dict[str, Any]]:
    """
    鐢熸垚澶氫釜鍦烘櫙鍊欓€夋柟妗?
    """
    if llm is None:
        llm = get_llm()
    candidates: List[Dict[str, Any]] = []
    for index in range(count):
        hint = f"璇锋彁渚涚{index + 1}涓笉鍚岃搴︾殑鍦烘櫙鏂规銆?"
        feedback = f"{user_feedback}；{hint}" if user_feedback else hint
        scenario_text = generate_scenario(
            topic=topic,
            grade_level=grade_level,
            duration=duration,
            context_summary=context_summary,
            knowledge_snippets=knowledge_snippets,
            user_feedback=feedback,
            llm=llm,
        )
        candidate_id = chr(65 + index)
        title = parse_scenario_title(scenario_text)
        candidates.append(
            {
                "id": candidate_id,
                "title": title or f"鏂规 {candidate_id}",
                "scenario": scenario_text,
                "rationale": "",
            }
        )
    return candidates


# 工具元信息（供 Action Node 使用）
TOOL_INFO = {
    "name": "generate_scenario",
    "description": "根据课程主题、年级和上下文生成引人入胜的教学场景",
    "inputs": ["topic", "grade_level", "duration", "context_summary", "knowledge_snippets", "user_feedback"],
    "output": "scenario",
    "updates_progress": "scenario",
}
