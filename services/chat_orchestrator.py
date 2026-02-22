from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from langchain_core.prompts import ChatPromptTemplate

from adapters.llm import LLMInvocationError, get_llm
from core.models import ToolSeed
from core.types import EntryPoint
from utils.intake import intake_to_constraints, normalize_intake


ALGORITHM_KEYWORDS = {
    "kmeans",
    "k-means",
    "k means",
    "k均值",
    "k 均值",
    "k-均值",
    "knn",
    "k近邻",
    "最近邻",
    "svm",
    "bayes",
    "naive bayes",
    "decision tree",
    "random forest",
    "xgboost",
    "聚类",
    "分类",
    "回归",
    "监督学习",
    "无监督学习",
    "机器学习",
    "深度学习",
    "算法",
    "知识点",
}

TOOL_KEYWORDS = {
    "orange",
    "橙子",
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

SCENARIO_KEYWORDS = {"场景", "情境", "scenario"}
TOOL_TRIGGER_KEYWORDS = {
    "工具",
    "软件",
    "实验",
    "活动",
    "驱动问题",
    "驱动性问题",
    "driving question",
    "question chain",
    "project",
    "activity",
    "experiment",
}.union(TOOL_KEYWORDS)


def _contains_keyword(text: str, keywords: set[str]) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        raise ValueError("Empty LLM response")
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return json.loads(match.group(0))


def _build_entry_question(intake: Dict[str, Any]) -> str:
    prompt = (
        "你是课程助手。用户已填写课程信息，请用一句自然的中文问题询问："
        "他们希望从哪里开始（场景 / 工具 / 实验 / 活动 / 驱动问题）。"
        "不要输出多余内容，只输出一句话。"
    )
    try:
        llm = get_llm()
        chain = ChatPromptTemplate.from_template("{text}") | llm
        result = chain.invoke({"text": prompt})
        return (result.content or "").strip() or "你希望从哪里开始？场景 / 工具 / 实验 / 活动 / 驱动问题"
    except Exception:
        return "你希望从哪里开始？场景 / 工具 / 实验 / 活动 / 驱动问题"


def _build_tool_seed_prompt(message: str, intake: Dict[str, Any], existing: Optional[Dict[str, Any]]) -> str:
    intake_text = json.dumps(intake, ensure_ascii=False)
    existing_text = json.dumps(existing or {}, ensure_ascii=False)
    return (
        "你是 PBL 课程助手，请从用户输入中抽取 tool_seed。"
        "只输出严格 JSON，不要多余文字：\n"
        "{\n"
        '  "tool_seed": {\n'
        '    "tool_name": "string",\n'
        '    "algorithms": ["..."],\n'
        '    "affordances": ["..."],\n'
        '    "user_intent": "string",\n'
        '    "constraints": {}\n'
        "  },\n"
        '  "question": "string or null"\n'
        "}\n"
        "规则：\n"
        "- 如果信息不足以确定 tool_name 或 user_intent，请给出一个单句追问放在 question。\n"
        "- tool_seed 可以是部分字段，但不要编造不存在的工具。\n"
        f"已有 intake: {intake_text}\n"
        f"已有 tool_seed: {existing_text}\n"
        f"用户输入: {message}\n"
    )


def _build_fallback_prompt(history: str, message: str) -> str:
    return f"""
你是 PBL 任务入口助手。请根据用户输入判断入口并补齐信息。
只输出严格 JSON，禁止输出多余文字：
{{
  "status": "ask" | "ready",
  "entry_point": "scenario" | "tool_seed" | null,
  "scenario": string | null,
  "tool_seed": object | null,
  "question": string | null
}}
规则：
- 需要更多信息时，status=ask，并给出一个明确问题。
- 准备就绪时，status=ready，并提供 entry_point 为 scenario/tool_seed。
- tool_seed 至少包含 tool_name 与 user_intent。

对话历史：
{history}

用户输入：
{message}
""".strip()


def _detect_entry_choice(message: str) -> Optional[EntryPoint]:
    text = message or ""
    if _contains_keyword(text, SCENARIO_KEYWORDS):
        return EntryPoint.scenario
    if _contains_keyword(text, TOOL_TRIGGER_KEYWORDS):
        return EntryPoint.tool_seed
    return None


def _infer_tool_name(message: str) -> str:
    lower = (message or "").lower()
    for keyword in TOOL_KEYWORDS:
        if keyword in lower:
            return keyword
    return "通用工具"


def _extract_tool_seed_with_llm(
    message: str,
    intake: Dict[str, Any],
    existing: Optional[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    prompt = _build_tool_seed_prompt(message, intake, existing)
    try:
        llm = get_llm()
        chain = ChatPromptTemplate.from_template("{text}") | llm
        result = chain.invoke({"text": prompt})
    except Exception as exc:
        raise LLMInvocationError("LLM invocation failed for tool_seed extraction") from exc
    data = _extract_json(result.content or "")
    tool_seed = data.get("tool_seed") if isinstance(data.get("tool_seed"), dict) else None
    question = data.get("question") if isinstance(data.get("question"), str) else None
    return tool_seed, question


def _generate_starter_scenario(intake: Dict[str, Any]) -> str:
    prompt = (
        "你是课程设计助手。请基于以下信息生成一个简短教学场景（2-4句）。"
        "只输出严格 JSON：{\"scenario\":\"...\"}\n"
        f"信息：{json.dumps(intake, ensure_ascii=False)}"
    )
    try:
        llm = get_llm()
        chain = ChatPromptTemplate.from_template("{text}") | llm
        result = chain.invoke({"text": prompt})
        data = _extract_json(result.content or "")
        scenario = data.get("scenario")
        if isinstance(scenario, str) and scenario.strip():
            return scenario.strip()
    except Exception:
        pass
    return "请基于所学知识设计一个贴近学生生活的项目式学习场景。"


class ChatSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.messages: List[Dict[str, str]] = []
        self.intake: Dict[str, Any] = {}
        self.awaiting_entry: bool = False
        self.awaiting_tool_seed: bool = False
        self.entry_asked: bool = False
        self.tool_seed_partial: Optional[Dict[str, Any]] = None
        self.tool_seed_ask_count: int = 0

    def append(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})


class ChatSessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, ChatSession] = {}

    def get(self, session_id: str) -> Optional[ChatSession]:
        return self._sessions.get(session_id)

    def create(self) -> ChatSession:
        session = ChatSession(uuid4().hex)
        self._sessions[session.session_id] = session
        return session


def _finalize_tool_seed(
    tool_seed: Dict[str, Any],
    intake: Dict[str, Any],
    message: str,
) -> Dict[str, Any]:
    allowed_keys = {"tool_name", "algorithms", "affordances", "constraints", "user_intent"}
    tool_seed = {k: v for k, v in tool_seed.items() if k in allowed_keys}
    constraints = tool_seed.get("constraints") if isinstance(tool_seed.get("constraints"), dict) else {}
    constraints = {**constraints, **intake_to_constraints(intake)}
    constraints.setdefault("context_summary", message.strip())
    tool_seed["constraints"] = constraints
    tool_seed.setdefault("algorithms", [])
    tool_seed.setdefault("affordances", [])
    if not tool_seed.get("tool_name"):
        tool_seed["tool_name"] = _infer_tool_name(message)
    if not tool_seed.get("user_intent"):
        tool_seed["user_intent"] = intake.get("knowledge_point") or "项目式学习"
    return tool_seed


def _handle_tool_seed_entry(
    session: ChatSession,
    message: str,
) -> Dict[str, Any]:
    intake = session.intake
    tool_seed, question = _extract_tool_seed_with_llm(message, intake, session.tool_seed_partial)
    if isinstance(tool_seed, dict):
        session.tool_seed_partial = tool_seed
    if not isinstance(tool_seed, dict):
        tool_seed = session.tool_seed_partial or {}
    tool_seed = _finalize_tool_seed(tool_seed, intake, message)
    missing = not tool_seed.get("tool_name") or not tool_seed.get("user_intent")
    if missing and session.tool_seed_ask_count < 1 and question:
        session.tool_seed_ask_count += 1
        session.awaiting_tool_seed = True
        session.append("assistant", question)
        return {
            "status": "ask",
            "assistant_message": question,
            "entry_point": None,
            "entry_data": None,
        }
    session.awaiting_tool_seed = False
    try:
        ToolSeed(**tool_seed)
    except Exception:
        tool_seed = _finalize_tool_seed(tool_seed, intake, message)
    assistant_message = "已收到信息，开始创建任务并进入场景生成。"
    session.append("assistant", assistant_message)
    return {
        "status": "ready",
        "assistant_message": assistant_message,
        "entry_point": EntryPoint.tool_seed,
        "entry_data": tool_seed,
    }


def _handle_scenario_entry(
    session: ChatSession,
    message: str,
) -> Dict[str, Any]:
    intake = session.intake
    scenario_text = ""
    if message and len(message.strip()) > 12 and not _contains_keyword(message, TOOL_TRIGGER_KEYWORDS):
        scenario_text = message.strip()
    if not scenario_text:
        scenario_text = _generate_starter_scenario(intake)
    constraints = intake_to_constraints(intake)
    entry_data = {
        "scenario": scenario_text,
        "constraints": constraints,
        "user_intent": intake.get("knowledge_point") or "",
        "tool_name": intake.get("knowledge_point") or "topic",
        "intake": intake,
    }
    assistant_message = "已收到场景信息，开始创建任务。"
    session.append("assistant", assistant_message)
    return {
        "status": "ready",
        "assistant_message": assistant_message,
        "entry_point": EntryPoint.scenario,
        "entry_data": entry_data,
    }


def handle_chat_message(
    *,
    session: ChatSession,
    message: str,
    intake: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if intake:
        normalized = normalize_intake(intake)
        session.intake = normalized
        session.awaiting_entry = True
        session.awaiting_tool_seed = False
        session.entry_asked = False
        session.tool_seed_partial = None
        session.tool_seed_ask_count = 0
        question = _build_entry_question(normalized)
        session.entry_asked = True
        session.append("assistant", question)
        return {
            "status": "ask",
            "assistant_message": question,
            "entry_point": None,
            "entry_data": None,
        }

    session.append("user", message or "")
    if session.awaiting_tool_seed:
        return _handle_tool_seed_entry(session, message)
    if session.awaiting_entry:
        choice = _detect_entry_choice(message)
        if choice is None:
            question = _build_entry_question(session.intake)
            session.append("assistant", question)
            return {
                "status": "ask",
                "assistant_message": question,
                "entry_point": None,
                "entry_data": None,
            }
        session.awaiting_entry = False
        if choice == EntryPoint.tool_seed:
            return _handle_tool_seed_entry(session, message)
        return _handle_scenario_entry(session, message)

    # fallback to previous LLM-driven routing (for API compatibility)
    llm = get_llm()
    history = "\n".join([f"{m['role']}: {m['content']}" for m in session.messages[-8:]])
    prompt = ChatPromptTemplate.from_template("{text}")
    try:
        chain = prompt | llm
        result = chain.invoke({"text": _build_fallback_prompt(history, message)})
    except Exception as exc:
        raise LLMInvocationError("LLM invocation failed for chat") from exc

    data = _extract_json(result.content or "")
    status = data.get("status")
    entry_point = data.get("entry_point")
    scenario = data.get("scenario")
    tool_seed = data.get("tool_seed")
    question = data.get("question") or ""

    if status not in {"ask", "ready"}:
        status = "ask"
        question = "请补充：你想从工具/软件开始还是从教学场景开始？"

    if status == "ask":
        question = question or "请补充：你想从工具/软件开始还是从教学场景开始？"
        session.append("assistant", question)
        return {
            "status": "ask",
            "assistant_message": question,
            "entry_point": None,
            "entry_data": None,
        }

    if entry_point == "tool_seed":
        if not isinstance(tool_seed, dict):
            question = "请补充 tool_seed 的 JSON（至少包含 tool_name 与 user_intent）。"
            session.append("assistant", question)
            return {
                "status": "ask",
                "assistant_message": question,
                "entry_point": None,
                "entry_data": None,
            }
        assistant_message = "已获取 tool_seed，开始创建任务。"
        session.append("assistant", assistant_message)
        return {
            "status": "ready",
            "assistant_message": assistant_message,
            "entry_point": EntryPoint.tool_seed,
            "entry_data": tool_seed,
        }

    if entry_point == "scenario":
        scenario_text = scenario
        if isinstance(scenario_text, dict):
            scenario_text = scenario_text.get("scenario", "")
        if not scenario_text:
            question = "请提供一个简短的教学场景描述（年级、时长、目标）。"
            session.append("assistant", question)
            return {
                "status": "ask",
                "assistant_message": question,
                "entry_point": None,
                "entry_data": None,
            }
        entry_data = scenario if isinstance(scenario, dict) else {"scenario": scenario_text}
        assistant_message = "已获取场景信息，开始创建任务。"
        session.append("assistant", assistant_message)
        return {
            "status": "ready",
            "assistant_message": assistant_message,
            "entry_point": EntryPoint.scenario,
            "entry_data": entry_data,
        }

    question = "请说明你想从工具/软件开始还是从教学场景开始？"
    session.append("assistant", question)
    return {
        "status": "ask",
        "assistant_message": question,
        "entry_point": None,
        "entry_data": None,
    }


__all__ = ["ChatSessionStore", "handle_chat_message"]
