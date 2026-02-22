from __future__ import annotations

import json
import os
import re
from typing import List, Optional, Tuple

from langchain_core.prompts import ChatPromptTemplate

from adapters.llm import LLMInvocationError, get_llm
from core.models import EntryDecision
from core.types import EntryPoint


STRONG_SCENARIO_PHRASES = {
    "从场景开始",
    "从情境开始",
    "从场景",
    "从情境",
    "start from scenario",
    "from scenario",
}

STRONG_TOOL_PHRASES = {
    "从工具开始",
    "从实验开始",
    "从活动开始",
    "从驱动问题开始",
    "从项目开始",
    "从工具",
    "从实验",
    "从活动",
    "从驱动问题",
    "start from tool",
    "start from experiment",
    "start from activity",
    "start from driving question",
}

SCENARIO_KEYWORDS = {
    "场景",
    "情境",
    "真实任务",
    "生活问题",
    "scenario",
}

TOOL_KEYWORDS = {
    "工具",
    "软件",
    "实验",
    "活动",
    "驱动问题",
    "项目任务",
    "project",
    "activity",
    "experiment",
    "driving question",
    "question chain",
    "orange",
    "weka",
    "scratch",
    "python",
    "jupyter",
    "colab",
    "excel",
    "power bi",
    "pytorch",
    "tensorflow",
    "sklearn",
    "scikit",
    "matlab",
    "rapidminer",
}


def _contains(text: str, keywords: set[str]) -> List[str]:
    lowered = (text or "").lower()
    return [kw for kw in keywords if kw in lowered]


def _apply_strong_signals(text: str) -> Tuple[Optional[EntryPoint], List[str]]:
    scenario_hits = _contains(text, STRONG_SCENARIO_PHRASES)
    tool_hits = _contains(text, STRONG_TOOL_PHRASES)
    if scenario_hits and tool_hits:
        hits = [f"strong:scenario:{h}" for h in scenario_hits] + [
            f"strong:tool_seed:{h}" for h in tool_hits
        ]
        return None, hits
    if scenario_hits:
        return EntryPoint.scenario, [f"strong:scenario:{h}" for h in scenario_hits]
    if tool_hits:
        return EntryPoint.tool_seed, [f"strong:tool_seed:{h}" for h in tool_hits]
    return None, []


def _apply_keyword_rules(text: str) -> Tuple[Optional[EntryPoint], List[str]]:
    scenario_hits = _contains(text, SCENARIO_KEYWORDS)
    tool_hits = _contains(text, TOOL_KEYWORDS)
    if scenario_hits and tool_hits:
        hits = [f"keyword:scenario:{h}" for h in scenario_hits] + [
            f"keyword:tool_seed:{h}" for h in tool_hits
        ]
        return None, hits
    if scenario_hits:
        return EntryPoint.scenario, [f"keyword:scenario:{h}" for h in scenario_hits]
    if tool_hits:
        return EntryPoint.tool_seed, [f"keyword:tool_seed:{h}" for h in tool_hits]
    return None, []


def _extract_json(text: str) -> dict:
    if not text:
        raise ValueError("Empty LLM response")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = cleaned.strip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
    raise ValueError("No JSON object found in LLM response")


def _llm_fallback(text: str) -> EntryDecision:
    prompt = (
        "你是入口判断器，请根据用户话语判断入口。"
        "只输出 JSON：\n"
        "{\n"
        '  "entry_point": "scenario" | "tool_seed",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "reason": "string"\n'
        "}\n"
        f"用户话语：{text}\n"
    )
    try:
        llm = get_llm()
        chain = ChatPromptTemplate.from_template("{text}") | llm
        result = chain.invoke({"text": prompt})
    except Exception as exc:
        raise LLMInvocationError("LLM invocation failed for entry decision") from exc
    data = _extract_json(result.content or "")
    entry_point = data.get("entry_point") or "scenario"
    confidence = float(data.get("confidence", 0.5))
    reason = str(data.get("reason", "")).strip()
    return EntryDecision(
        chosen_entry_point=EntryPoint(entry_point),
        rules_hit=[],
        model_reason=reason or "llm_fallback",
        confidence=max(0.0, min(1.0, confidence)),
    )


def resolve_entry_decision(text: str) -> EntryDecision:
    choice, rules_hit = _apply_strong_signals(text)
    if choice is not None:
        return EntryDecision(
            chosen_entry_point=choice,
            rules_hit=rules_hit,
            model_reason="strong_signal",
            confidence=0.95,
        )
    choice, keyword_hits = _apply_keyword_rules(text)
    if choice is not None:
        return EntryDecision(
            chosen_entry_point=choice,
            rules_hit=rules_hit + keyword_hits,
            model_reason="keyword_rule",
            confidence=0.75,
        )
    decision = _llm_fallback(text)
    if rules_hit:
        decision.rules_hit = rules_hit
    return decision


def get_entry_threshold() -> float:
    value = os.getenv("ENTRY_CONFIDENCE_THRESHOLD", "0.65")
    try:
        return max(0.0, min(1.0, float(value)))
    except ValueError:
        return 0.65


__all__ = ["resolve_entry_decision", "get_entry_threshold"]
