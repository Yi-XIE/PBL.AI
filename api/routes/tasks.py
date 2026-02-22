from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError, model_validator

from adapters.llm import LLMInvocationError, LLMNotConfigured
from core.models import DecisionResult, EntryDecision, StageArtifact, Task, ToolSeed
from core.types import ActionType, EntryPoint
from services.chat_orchestrator import (
    ChatSessionStore,
    handle_chat_message,
    handle_task_chat_message,
)
from services.orchestrator import Orchestrator
from services.plan_builder import build_course_plan
from services.sse_bus import SSEBus
from services.task_store import InMemoryTaskStore, JsonPersistence
from utils.serialization import to_jsonable


router = APIRouter()
store = InMemoryTaskStore()
persistence = JsonPersistence()
sse_bus = SSEBus()
orchestrator = Orchestrator(store, persistence, sse_bus)
chat_store = ChatSessionStore()


class TaskCreateRequest(BaseModel):
    entry_point: EntryPoint
    scenario: Optional[Any] = None
    tool_seed: Optional[Any] = None


class TaskCreateResponse(BaseModel):
    task: Task
    decision: DecisionResult
    current_stage_artifact: Optional[StageArtifact] = None


class ActionRequest(BaseModel):
    action_type: Optional[ActionType] = None
    action: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    candidate_id: Optional[str] = None
    target_component: Optional[str] = None
    stage: Optional[str] = None
    feedback: Optional[str] = None
    option: Optional[str] = None
    conflict_id: Optional[str] = None

    @model_validator(mode="after")
    def normalize_action(self) -> "ActionRequest":
        if self.action_type is None and self.action:
            alias = self.action.lower()
            mapping = {
                "accept": ActionType.finalize_stage,
                "finalize": ActionType.finalize_stage,
                "finalize_stage": ActionType.finalize_stage,
                "select": ActionType.select_candidate,
                "select_candidate": ActionType.select_candidate,
                "regenerate": ActionType.regenerate_candidates,
                "regenerate_candidates": ActionType.regenerate_candidates,
                "feedback": ActionType.provide_feedback,
                "provide_feedback": ActionType.provide_feedback,
                "resolve_conflict": ActionType.resolve_conflict,
            }
            self.action_type = mapping.get(alias)
            if self.action_type is None:
                try:
                    self.action_type = ActionType(alias)
                except ValueError:
                    self.action_type = None
        if self.action_type is None:
            raise ValueError("action_type is required")
        payload = dict(self.payload or {})
        if "stage" not in payload:
            stage_value = self.stage or self.target_component
            if stage_value:
                payload["stage"] = stage_value
        if self.candidate_id and "candidate_id" not in payload:
            payload["candidate_id"] = self.candidate_id
        if self.feedback and "feedback" not in payload:
            payload["feedback"] = self.feedback
        if self.option and "option" not in payload:
            payload["option"] = self.option
        if self.conflict_id and "conflict_id" not in payload:
            payload["conflict_id"] = self.conflict_id
        self.payload = payload
        return self


class ActionResponse(BaseModel):
    task: Task
    decision: DecisionResult
    current_stage_artifact: Optional[StageArtifact] = None


class ProgressResponse(BaseModel):
    task_id: str
    current_stage: str
    completed_stages: list[str]
    status: str
    stage_status: str


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    task_id: Optional[str] = None
    intake: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    session_id: str
    status: str
    assistant_message: str
    entry_point: Optional[EntryPoint] = None
    entry_data: Optional[Any] = None
    task_id: Optional[str] = None
    entry_decision: Optional[EntryDecision] = None


class CoursePlanSection(BaseModel):
    stage: str
    title: str = ""
    candidate_id: Optional[str] = None
    content: Optional[Any] = None
    raw: Optional[Any] = None


class CoursePlanResponse(BaseModel):
    task_id: str
    sections: list[CoursePlanSection]


def _log_chat_trace(
    *,
    task: Optional[Task],
    session_id: str,
    message: str,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    tracer = orchestrator.tracer
    if tracer is None:
        return
    metadata = {
        "trace_type": "creative_dialogue",
        "session_id": session_id,
    }
    if task is not None:
        metadata["task_id"] = task.task_id
        metadata["stage"] = task.current_stage.value
        metadata["dialogue_state"] = task.dialogue_state.value
    inputs = {"message": message or "", "task_id": task.task_id if task else None}
    outputs = {
        "status": result.get("status") if result else None,
        "assistant_message": result.get("assistant_message") if result else None,
        "dialogue_action": result.get("dialogue_action") if result else None,
    }
    tracer.log_child(
        root_run_id=task.trace_root_id if task else None,
        name="chat:dialogue",
        run_type="chain",
        inputs=inputs,
        outputs=outputs,
        metadata=metadata,
        error=error,
    )


@router.post("/tasks", response_model=TaskCreateResponse)
async def create_task(request: TaskCreateRequest) -> TaskCreateResponse:
    entry_point = request.entry_point
    entry_data: Dict[str, Any] = {}
    if entry_point == EntryPoint.tool_seed:
        if request.tool_seed is None:
            raise HTTPException(status_code=400, detail="tool_seed is required")
        entry_data = request.tool_seed if isinstance(request.tool_seed, dict) else request.tool_seed.dict()
        try:
            ToolSeed(**entry_data)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=exc.errors()) from exc
    else:
        if request.scenario is None:
            raise HTTPException(status_code=400, detail="scenario is required")
        if isinstance(request.scenario, dict):
            entry_data = request.scenario
        else:
            entry_data = {"scenario": request.scenario}
    try:
        task, decision, artifact = orchestrator.create_task(entry_point, entry_data)
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMInvocationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TaskCreateResponse(task=task, decision=decision, current_stage_artifact=artifact)


@router.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: str) -> Task:
    task = store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tasks/{task_id}/progress", response_model=ProgressResponse)
async def get_progress(task_id: str) -> ProgressResponse:
    task = store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return ProgressResponse(
        task_id=task.task_id,
        current_stage=task.current_stage.value,
        completed_stages=[s.value for s in task.completed_stages],
        status=task.status,
        stage_status=task.stage_status.value,
    )


@router.get("/tasks/{task_id}/plan", response_model=CoursePlanResponse)
async def get_plan(task_id: str) -> CoursePlanResponse:
    task = store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    plan = build_course_plan(task)
    return CoursePlanResponse(**plan)


@router.post("/tasks/{task_id}/action", response_model=ActionResponse)
async def apply_action(task_id: str, request: ActionRequest) -> ActionResponse:
    try:
        task, decision, artifact = orchestrator.apply_action(
            task_id, request.action_type, request.payload
        )
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMInvocationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ActionResponse(task=task, decision=decision, current_stage_artifact=artifact)


@router.post("/chat", response_model=ChatResponse)
async def chat_entry(request: ChatRequest) -> ChatResponse:
    session = None
    if request.session_id:
        session = chat_store.get(request.session_id)
    if session is None:
        session = chat_store.create()

    task: Optional[Task] = None
    try:
        if request.task_id:
            task = store.get(request.task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            result = handle_task_chat_message(task=task, message=request.message)
            store.save(task)
            persistence.save_snapshot(task)
        else:
            result = handle_chat_message(
                session=session,
                message=request.message,
                intake=request.intake,
            )
    except LLMNotConfigured as exc:
        _log_chat_trace(task=task, session_id=session.session_id, message=request.message, error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMInvocationError as exc:
        _log_chat_trace(task=task, session_id=session.session_id, message=request.message, error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        _log_chat_trace(task=task, session_id=session.session_id, message=request.message, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    status = result["status"]
    entry_point = result.get("entry_point")
    entry_data = result.get("entry_data")

    task_id: Optional[str] = None
    if status == "ready" and entry_point is not None and entry_data is not None:
        try:
            task, _, _ = orchestrator.create_task(
                entry_point,
                entry_data,
                entry_decision=result.get("entry_decision"),
            )
        except LLMNotConfigured as exc:
            _log_chat_trace(task=task, session_id=session.session_id, message=request.message, error=str(exc))
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except LLMInvocationError as exc:
            _log_chat_trace(task=task, session_id=session.session_id, message=request.message, error=str(exc))
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        task_id = task.task_id

    _log_chat_trace(task=task, session_id=session.session_id, message=request.message, result=result)

    return ChatResponse(
        session_id=session.session_id,
        status=status,
        assistant_message=result.get("assistant_message", ""),
        entry_point=entry_point,
        entry_data=entry_data,
        task_id=task_id or (task.task_id if task else None),
        entry_decision=result.get("entry_decision"),
    )


@router.get("/tasks/{task_id}/events")
async def stream_events(task_id: str) -> StreamingResponse:
    async def event_stream():
        async for item in sse_bus.stream(task_id):
            payload = json.dumps(to_jsonable(item["data"]), ensure_ascii=False, default=str)
            yield f"event: {item['event']}\ndata: {payload}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
