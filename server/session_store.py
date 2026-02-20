from typing import Any, Dict, List, Optional
from uuid import uuid4


SESSIONS: Dict[str, Dict[str, Any]] = {}


def create_session(
    config: Dict[str, Any],
    state: Dict[str, Any],
    task: Optional[Dict[str, Any]] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
) -> str:
    session_id = uuid4().hex
    SESSIONS[session_id] = {
        "config": config,
        "state": state,
        "generation_count": 0,
        "task": task,
        "messages": messages or [],
    }
    return session_id


def get_session(session_id: str) -> Dict[str, Any]:
    return SESSIONS.get(session_id)


def update_state(session_id: str, state: Dict[str, Any]) -> None:
    if session_id in SESSIONS:
        SESSIONS[session_id]["state"] = state


def update_config(session_id: str, config: Dict[str, Any]) -> None:
    if session_id in SESSIONS:
        SESSIONS[session_id]["config"] = config


def update_task(session_id: str, task: Dict[str, Any]) -> None:
    if session_id in SESSIONS:
        SESSIONS[session_id]["task"] = task


def set_messages(session_id: str, messages: List[Dict[str, Any]]) -> None:
    if session_id in SESSIONS:
        SESSIONS[session_id]["messages"] = messages


def append_messages(session_id: str, messages: List[Dict[str, Any]]) -> None:
    if session_id in SESSIONS:
        current = SESSIONS[session_id].setdefault("messages", [])
        current.extend(messages)


def increment_generation(session_id: str) -> int:
    if session_id in SESSIONS:
        current = SESSIONS[session_id].get("generation_count", 0) + 1
        SESSIONS[session_id]["generation_count"] = current
        return current
    return 0


def reset_generation(session_id: str) -> None:
    if session_id in SESSIONS:
        SESSIONS[session_id]["generation_count"] = 0
