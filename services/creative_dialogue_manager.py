from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate

from adapters.llm import LLMInvocationError, get_llm
from core.models import CreativeContext


def _extract_json(text: str) -> Dict[str, Any]:
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


class CreativeDialogueManager:
    def extract_intent_update(
        self,
        context: CreativeContext,
        user_input: str,
        intake: Optional[Dict[str, Any]] = None,
        recent_messages: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        prompt = (
            "你是课程共创助手。请从用户对话中提炼创作意图与关键约束。\n"
            "只输出严格 JSON，不要多余文字：\n"
            "{\n"
            '  "intent": "string or empty",\n'
            '  "key_constraints": ["topic:...", "grade:...", "duration:...", "classroom:..."] ,\n'
            '  "anchor_concepts": ["..."],\n'
            '  "needs_confirmation": true|false,\n'
            '  "question": "string or null",\n'
            '  "summary": "string"\n'
            "}\n"
            "规则：\n"
            "- 若用户意图模糊/信息不足，needs_confirmation=true，并给出一句澄清问题。\n"
            "- 若能提炼意图，needs_confirmation=false，summary 用一句话概括。\n"
            "- key_constraints 仅保留最重要 3-5 个。\n"
            "- 不要编造不存在的信息。\n\n"
            f"已有意图: {context.original_intent}\n"
            f"已有约束: {context.key_constraints}\n"
            f"锚点概念: {context.anchor_concepts}\n"
            f"Intake: {json.dumps(intake or {}, ensure_ascii=False)}\n"
            f"最近对话: {json.dumps(recent_messages or [], ensure_ascii=False)}\n"
            f"用户输入: {user_input}\n"
        )
        try:
            llm = get_llm(purpose="decision")
            chain = ChatPromptTemplate.from_template("{text}") | llm
            result = chain.invoke({"text": prompt})
            data = _extract_json(result.content or "")
        except Exception as exc:
            raise LLMInvocationError("LLM invocation failed for creative dialogue") from exc

        intent = str(data.get("intent") or "").strip()
        key_constraints = data.get("key_constraints") or []
        if isinstance(key_constraints, dict):
            key_constraints = [f"{k}:{v}" for k, v in key_constraints.items() if v]
        if isinstance(key_constraints, str):
            key_constraints = [key_constraints]
        key_constraints = [str(item).strip() for item in key_constraints if str(item).strip()]

        anchor_concepts = data.get("anchor_concepts") or []
        if isinstance(anchor_concepts, str):
            anchor_concepts = [anchor_concepts]
        anchor_concepts = [str(item).strip() for item in anchor_concepts if str(item).strip()]

        needs_confirmation = bool(data.get("needs_confirmation", False))
        question = data.get("question")
        if question is not None:
            question = str(question).strip()
        summary = str(data.get("summary") or "").strip()

        if needs_confirmation and not question:
            question = "我需要更明确的目标/场景/工具信息，能补充一句吗？"

        return {
            "intent": intent,
            "key_constraints": key_constraints,
            "anchor_concepts": anchor_concepts,
            "needs_confirmation": needs_confirmation,
            "question": question,
            "summary": summary,
        }


__all__ = ["CreativeDialogueManager"]
