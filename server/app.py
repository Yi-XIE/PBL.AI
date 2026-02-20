import os
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import config
from graph.workflow import run_workflow_step
from state.agent_state import create_initial_state
from server.models import (
    ActionRequest,
    FileUpdateRequest,
    SessionCreateRequest,
    SessionResponse,
    ToolRequest,
)
from server.session_store import (
    create_session,
    get_session,
    increment_generation,
    reset_generation,
    update_config,
    update_state,
    update_task,
    append_messages,
)
from server.output_store import write_generation_snapshot
from server.state_ops import apply_file_update, build_user_input, determine_start_from
from server.virtual_files import build_virtual_files
from server.task_manager import create_task, refresh_task
from server.decision_layer import decide_next
from server.message_manager import (
    build_status_message,
    build_knowledge_message,
    build_decision_messages,
    append_messages as append_message_list,
)


APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
WEB_DIST = os.path.join(PROJECT_ROOT, "web", "dist")


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_session(session_id: str) -> Dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _build_response(session_id: str, state: Dict[str, Any], error: Optional[str] = None) -> SessionResponse:
    session = get_session(session_id) or {}
    return SessionResponse(
        session_id=session_id,
        state=state,
        virtual_files=build_virtual_files(state),
        task=session.get("task"),
        messages=session.get("messages", []),
        error=error,
    )


def _ensure_api_key() -> Optional[str]:
    if not config.DEEPSEEK_API_KEY:
        return "DEEPSEEK_API_KEY is missing. Please set it in .env before generating."
    return None


def _create_state_from_request(request: SessionCreateRequest) -> Dict[str, Any]:
    user_input = build_user_input(
        request.user_input,
        request.topic,
        request.grade_level,
        request.duration,
    )
    start_from = determine_start_from(user_input, request.seed_components)
    return create_initial_state(
        user_input=user_input,
        topic=request.topic,
        grade_level=request.grade_level,
        duration=request.duration,
        classroom_context=request.classroom_context,
        classroom_mode=request.classroom_mode,
        start_from=start_from,
        provided_components=request.seed_components,
        hitl_enabled=request.hitl_enabled,
        cascade_default=request.cascade_default,
        interactive=False,
        multi_option=request.multi_option,
    )


def _sync_task_and_messages(session_id: str, state: Dict[str, Any], user_action: str) -> None:
    session = get_session(session_id) or {}
    task = session.get("task") or create_task(session_id, state)
    task = refresh_task(task, state)
    update_task(session_id, task)

    messages: List[Dict[str, Any]] = list(session.get("messages", []))
    status_message = build_status_message(task, state)
    additions: List[Dict[str, Any]] = []
    if status_message:
        additions.append(status_message)
    knowledge_message = build_knowledge_message(state)
    if knowledge_message and not any(
        msg.get("message") == knowledge_message.get("message") for msg in messages
    ):
        additions.append(knowledge_message)
    decision = decide_next(task, state, user_action)
    additions.extend(build_decision_messages(decision))
    messages = append_message_list(messages, additions)
    append_messages(session_id, messages[len(session.get("messages", [])):])


@app.post("/api/sessions", response_model=SessionResponse)
def create_session_api(request: SessionCreateRequest) -> SessionResponse:
    config_payload = request.model_dump()
    state = _create_state_from_request(request)
    config_payload["start_from"] = state.get("start_from", config_payload.get("start_from"))
    session_id = create_session(config_payload, state)
    update_task(session_id, create_task(session_id, state))

    error = None
    should_generate = bool(state.get("user_input") or request.topic or request.seed_components)
    if should_generate:
        error = _ensure_api_key()
        if not error:
            try:
                state = run_workflow_step(state)
                update_state(session_id, state)
                generation_index = increment_generation(session_id)
                write_generation_snapshot(session_id, state, generation_index)
                _sync_task_and_messages(session_id, state, "start")
            except Exception as exc:  # pragma: no cover - surface to UI
                error = str(exc)

    return _build_response(session_id, state, error)


@app.get("/api/sessions/{session_id}", response_model=SessionResponse)
def get_session_api(session_id: str) -> SessionResponse:
    session = _require_session(session_id)
    state = session["state"]
    if not session.get("task"):
        update_task(session_id, create_task(session_id, state))
    return _build_response(session_id, state)


@app.post("/api/sessions/{session_id}/actions", response_model=SessionResponse)
def session_action_api(session_id: str, request: ActionRequest) -> SessionResponse:
    session = _require_session(session_id)
    state = session["state"]
    error = None

    if request.action == "accept":
        if not state.get("await_user") or not state.get("pending_component"):
            raise HTTPException(status_code=400, detail="No pending component to accept.")
        state["user_decision"] = "accept"
        state["user_feedback"] = None
        state["feedback_target"] = None
        state["selected_candidate_id"] = state.get("selected_candidate_id")
    elif request.action == "continue":
        if state.get("await_user"):
            raise HTTPException(status_code=400, detail="Awaiting user decision. Accept or regenerate first.")
    elif request.action == "regenerate":
        if not request.feedback:
            raise HTTPException(status_code=400, detail="Feedback is required for regenerate.")
        target = request.target_component or state.get("pending_component") or state.get("current_component")
        if target == "question_chain":
            target = "driving_question"
        if not target:
            raise HTTPException(status_code=400, detail="No target component available to regenerate.")
        state["await_user"] = True
        state["pending_component"] = target
        state["user_decision"] = "regenerate"
        state["feedback_target"] = target
        state["user_feedback"] = {target: request.feedback}
        state["pending_candidates"] = []
        state["selected_candidate_id"] = None
    elif request.action == "select_candidate":
        if not state.get("await_user") or not state.get("pending_component"):
            raise HTTPException(status_code=400, detail="No pending component to select.")
        if not request.candidate_id:
            raise HTTPException(status_code=400, detail="candidate_id is required.")
        state["user_decision"] = "select_candidate"
        state["selected_candidate_id"] = request.candidate_id
    elif request.action == "reset":
        config_payload = session.get("config", {})
        new_request = SessionCreateRequest(**config_payload)
        state = _create_state_from_request(new_request)
        update_state(session_id, state)
        update_config(session_id, config_payload)
        reset_generation(session_id)
        update_task(session_id, create_task(session_id, state))
        return _build_response(session_id, state)
    else:
        raise HTTPException(status_code=400, detail="Unknown action.")

    error = _ensure_api_key()
    if not error:
        try:
            state = run_workflow_step(state)
            update_state(session_id, state)
            generation_index = increment_generation(session_id)
            write_generation_snapshot(session_id, state, generation_index)
            _sync_task_and_messages(session_id, state, request.action)
        except Exception as exc:  # pragma: no cover - surface to UI
            error = str(exc)

    return _build_response(session_id, state, error)


@app.put("/api/sessions/{session_id}/files", response_model=SessionResponse)
def update_file_api(session_id: str, request: FileUpdateRequest) -> SessionResponse:
    session = _require_session(session_id)
    state = session["state"]

    try:
        state, _component = apply_file_update(
            state,
            request.path,
            request.content,
            cascade=request.cascade,
            lock=request.lock,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    update_state(session_id, state)
    _sync_task_and_messages(session_id, state, "edit")
    return _build_response(session_id, state)


@app.post("/api/sessions/{session_id}/tools", response_model=SessionResponse)
def trigger_tool_api(session_id: str, request: ToolRequest) -> SessionResponse:
    session = _require_session(session_id)
    state = session["state"]
    tool_name = request.tool
    messages = session.get("messages", [])
    additions = [
        {
            "id": uuid4().hex,
            "type": "tool_status",
            "message": f"正在调用工具：{tool_name}...",
            "stage": state.get("current_component") or state.get("pending_component") or "",
            "created_at": time.time(),
        },
        {
            "id": uuid4().hex,
            "type": "tool_status",
            "message": f"工具 {tool_name} 已完成（模拟）。",
            "stage": state.get("current_component") or state.get("pending_component") or "",
            "created_at": time.time(),
        },
    ]
    append_messages(session_id, additions)
    return _build_response(session_id, state)


@app.get("/api/sessions/{session_id}/export")
def export_session_api(session_id: str) -> JSONResponse:
    session = _require_session(session_id)
    state = session["state"]
    payload = {
        "metadata": {
            "topic": state.get("topic", ""),
            "grade_level": state.get("grade_level", ""),
            "duration": state.get("duration", 0),
        },
        "course_design": state.get("course_design", {}),
    }
    return JSONResponse(content=payload)


if os.path.isdir(WEB_DIST):
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
else:
    @app.get("/", include_in_schema=False)
    def root() -> HTMLResponse:
        message = (
            "<html><body style='font-family: sans-serif;'>"
            "<h2>Web UI not built</h2>"
            "<p>Run <code>npm install</code> and <code>npm run build</code> in <code>web/</code>, "
            "or start the dev server with <code>npm run dev</code>.</p>"
            "</body></html>"
        )
        return HTMLResponse(content=message)
