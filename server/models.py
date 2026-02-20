from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from typing_extensions import Literal


class SessionCreateRequest(BaseModel):
    user_input: str = ""
    topic: str = ""
    grade_level: str = "初中"
    duration: int = 80
    classroom_mode: str = "normal"
    classroom_context: str = ""
    start_from: str = "topic"
    seed_components: Dict[str, str] = Field(default_factory=dict)
    hitl_enabled: bool = True
    cascade_default: bool = True


class SessionResponse(BaseModel):
    session_id: str
    state: Dict[str, Any]
    virtual_files: Dict[str, Any]
    error: Optional[str] = None


class ActionRequest(BaseModel):
    action: Literal["accept", "regenerate", "continue", "reset"]
    target_component: Optional[str] = None
    feedback: Optional[str] = None


class FileUpdateRequest(BaseModel):
    path: str
    content: str
    cascade: bool = True
    lock: bool = True
