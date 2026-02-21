from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from core.types import CandidateStatus, ConflictSeverity, EntryPoint, StageStatus, StageType


class ToolSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    algorithms: List[str] = Field(default_factory=list)
    affordances: List[str] = Field(default_factory=list)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    user_intent: str


class Candidate(BaseModel):
    id: str
    title: str
    status: CandidateStatus = CandidateStatus.generated
    content: Dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    derived_from: List[str] = Field(default_factory=list)
    alignment_score: float = 0.0
    generation_context: Dict[str, Any] = Field(default_factory=dict)


class StageArtifact(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    stage: StageType = Field(validation_alias="stage_type", serialization_alias="stage_type")
    revision_id: str = Field(default_factory=lambda: uuid4().hex)
    status: StageStatus = StageStatus.initialized
    iteration_count: int = 0
    candidates: List[Candidate] = Field(default_factory=list)
    selected_candidate_id: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    generation_context: Dict[str, Any] = Field(default_factory=dict)


class Explanation(BaseModel):
    summary: str
    details: List[str] = Field(default_factory=list)


class DecisionResult(BaseModel):
    next_stage: Optional[StageType] = None
    direction: str = "forward"
    explanation: Optional[Explanation] = None
    user_message: str = ""
    constraints: Dict[str, Any] = Field(default_factory=dict)


class ConflictOption(BaseModel):
    option: str
    title: str
    description: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class Conflict(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conflict_id: str = Field(default_factory=lambda: uuid4().hex)
    stage: StageType
    severity: ConflictSeverity
    summary: str
    warnings: List[str] = Field(default_factory=list, validation_alias="checks")
    conflict_options: List[ConflictOption] = Field(
        default_factory=list,
        validation_alias="options",
        serialization_alias="conflict_options",
    )
    recommendation: str = ""
    resolved: bool = False
    resolved_option: Optional[str] = None


class Message(BaseModel):
    role: str
    text: str
    stage: Optional[StageType] = None
    kind: str = "assistant"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid4().hex)
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    entry_point: EntryPoint
    entry_data: Dict[str, Any] = Field(default_factory=dict)
    tool_seed: Optional[ToolSeed] = None
    current_stage: StageType
    completed_stages: List[StageType] = Field(default_factory=list)
    artifacts: Dict[StageType, StageArtifact] = Field(default_factory=dict)
    status: str = "in_progress"
    stage_status: StageStatus = StageStatus.initialized
    conflicts: Dict[StageType, List[Conflict]] = Field(default_factory=dict)
    last_decision: Optional[DecisionResult] = None
    messages: List[Message] = Field(default_factory=list)
    trace_root_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
