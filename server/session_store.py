from typing import Any, Dict
from uuid import uuid4


SESSIONS: Dict[str, Dict[str, Any]] = {}


def create_session(config: Dict[str, Any], state: Dict[str, Any]) -> str:
    session_id = uuid4().hex
    SESSIONS[session_id] = {"config": config, "state": state}
    return session_id


def get_session(session_id: str) -> Dict[str, Any]:
    return SESSIONS.get(session_id)


def update_state(session_id: str, state: Dict[str, Any]) -> None:
    if session_id in SESSIONS:
        SESSIONS[session_id]["state"] = state


def update_config(session_id: str, config: Dict[str, Any]) -> None:
    if session_id in SESSIONS:
        SESSIONS[session_id]["config"] = config
