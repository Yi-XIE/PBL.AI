from typing import Any, Dict, List, Optional

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
    multi_option: bool = True


class TaskModel(BaseModel):
    task_id: str
    session_id: str
    topic: str = ""
    stages: List[str] = Field(default_factory=list)
    current_stage: str = ""
    completed_stages: List[str] = Field(default_factory=list)
    status: Literal["active", "completed"] = "active"
    created_at: float


class MessageModel(BaseModel):
    id: str
    type: Literal["status", "explanation", "action", "tool_status"]
    message: str
    stage: Optional[str] = None
    created_at: float


class SessionResponse(BaseModel):
    session_id: str
    state: Dict[str, Any]
    virtual_files: Dict[str, Any]
    task: Optional[TaskModel] = None
    messages: List[MessageModel] = Field(default_factory=list)
    error: Optional[str] = None


class ActionRequest(BaseModel):
    action: Literal["accept", "regenerate", "continue", "reset", "select_candidate"]
    target_component: Optional[str] = None
    feedback: Optional[str] = None
    candidate_id: Optional[str] = None


class ToolRequest(BaseModel):
    tool: Literal["web_search"]
    query: str = ""


class FileUpdateRequest(BaseModel):
    path: str
    content: str
    cascade: bool = False
    lock: bool = True
