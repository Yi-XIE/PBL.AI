from __future__ import annotations

import json
import re
from typing import Dict, List, Optional
from uuid import uuid4

from langchain_core.prompts import ChatPromptTemplate

from adapters.llm import LLMInvocationError, get_llm
from core.models import ToolSeed
from core.types import EntryPoint


class ChatSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.messages: List[Dict[str, str]] = []

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


def _extract_json(text: str) -> Dict[str, object]:
    if not text:
        raise ValueError("Empty LLM response")
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return json.loads(match.group(0))


def _build_prompt(history: str, message: str) -> str:
    return (
        "你是 PBL 任务入口助手。请根据用户输入判断入口并补齐信息。\n"
        "只输出严格 JSON，禁止输出多余文字：\n"
        "{\n"
        '  "status": "ask" | "ready",\n'
        '  "entry_point": "scenario" | "tool_seed" | null,\n'
        '  "scenario": string | null,\n'
        '  "tool_seed": object | null,\n'
        '  "question": string | null\n'
        "}\n"
        "规则：\n"
        "- 需要更多信息时，status=ask，并给出一个明确问题。\n"
        "- 准备就绪时，status=ready，并提供 entry_point 与 scenario/tool_seed。\n"
        "- tool_seed 至少包含 tool_name 与 user_intent。\n\n"
        f"对话历史：\n{history}\n\n"
        f"用户输入：\n{message}\n"
    )


def handle_chat_message(
    *,
    session: ChatSession,
    message: str,
) -> Dict[str, object]:
    session.append("user", message)
    llm = get_llm()
    history = "\n".join([f"{m['role']}: {m['content']}" for m in session.messages[-8:]])
    prompt = ChatPromptTemplate.from_template("{text}")
    try:
        chain = prompt | llm
        result = chain.invoke({"text": _build_prompt(history, message)})
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
        try:
            ToolSeed(**tool_seed)
        except Exception:
            question = "tool_seed 信息不完整，请提供 tool_name 与 user_intent（可包含 constraints）。"
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
        if not scenario:
            question = "请提供一个简短的教学场景描述。"
            session.append("assistant", question)
            return {
                "status": "ask",
                "assistant_message": question,
                "entry_point": None,
                "entry_data": None,
            }
        entry_data = scenario if isinstance(scenario, dict) else {"scenario": scenario}
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
