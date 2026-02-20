import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import config
from graph.workflow import run_workflow_step
from state.agent_state import create_initial_state
from server.models import ActionRequest, FileUpdateRequest, SessionCreateRequest, SessionResponse
from server.session_store import create_session, get_session, update_config, update_state
from server.state_ops import apply_file_update, build_user_input
from server.virtual_files import build_virtual_files


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
    return SessionResponse(
        session_id=session_id,
        state=state,
        virtual_files=build_virtual_files(state),
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
    return create_initial_state(
        user_input=user_input,
        topic=request.topic,
        grade_level=request.grade_level,
        duration=request.duration,
        classroom_context=request.classroom_context,
        classroom_mode=request.classroom_mode,
        start_from=request.start_from,
        provided_components=request.seed_components,
        hitl_enabled=request.hitl_enabled,
        cascade_default=request.cascade_default,
        interactive=False,
    )


@app.post("/api/sessions", response_model=SessionResponse)
def create_session_api(request: SessionCreateRequest) -> SessionResponse:
    config_payload = request.model_dump()
    state = _create_state_from_request(request)
    session_id = create_session(config_payload, state)

    error = None
    should_generate = bool(state.get("user_input") or request.topic or request.seed_components)
    if should_generate:
        error = _ensure_api_key()
        if not error:
            try:
                state = run_workflow_step(state)
                update_state(session_id, state)
            except Exception as exc:  # pragma: no cover - surface to UI
                error = str(exc)

    return _build_response(session_id, state, error)


@app.get("/api/sessions/{session_id}", response_model=SessionResponse)
def get_session_api(session_id: str) -> SessionResponse:
    session = _require_session(session_id)
    state = session["state"]
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
    elif request.action == "reset":
        config_payload = session.get("config", {})
        new_request = SessionCreateRequest(**config_payload)
        state = _create_state_from_request(new_request)
        update_state(session_id, state)
        update_config(session_id, config_payload)
        return _build_response(session_id, state)
    else:
        raise HTTPException(status_code=400, detail="Unknown action.")

    error = _ensure_api_key()
    if not error:
        try:
            state = run_workflow_step(state)
            update_state(session_id, state)
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
