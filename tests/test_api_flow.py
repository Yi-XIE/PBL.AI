import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from api.app import app
import api.routes.tasks as tasks_module
from services.orchestrator import Orchestrator
from services.sse_bus import SSEBus
from services.task_store import InMemoryTaskStore, JsonPersistence


class FakeChatModel(Runnable):
    def __init__(self, *args, **kwargs) -> None:
        self._index = 0

    def invoke(self, input, config=None):  # type: ignore[override]
        text = ""
        if hasattr(input, "to_messages"):
            text = " ".join([m.content for m in input.to_messages()])
        else:
            text = str(input)
        if "entry_point" in text and "tool_seed" in text and "status" in text:
            payload = (
                '{"status":"ready","entry_point":"scenario",'
                '"scenario":"Test scenario","tool_seed":null,"question":null}'
            )
            return AIMessage(content=payload)
        return AIMessage(content="Stub response")


@pytest.fixture(autouse=True)
def _fake_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("LLM_REQUIRED", "true")
    monkeypatch.setattr("adapters.llm.ChatOpenAI", FakeChatModel)
    yield


@pytest.fixture()
def client(tmp_path):
    tasks_module.store = InMemoryTaskStore()
    tasks_module.persistence = JsonPersistence(base_dir=str(tmp_path))
    tasks_module.sse_bus = SSEBus()
    tasks_module.orchestrator = Orchestrator(
        tasks_module.store,
        tasks_module.persistence,
        tasks_module.sse_bus,
    )
    tasks_module.chat_store = tasks_module.ChatSessionStore()
    with TestClient(app) as client:
        yield client


def _artifact_stage(artifact: dict) -> str:
    return artifact.get("stage_type") or artifact.get("stage")


def _select_first_candidate(client: TestClient, task_id: str, stage: str, artifact: dict) -> dict:
    candidate_id = artifact["candidates"][0]["id"]
    response = client.post(
        f"/api/tasks/{task_id}/action",
        json={
            "action_type": "select_candidate",
            "payload": {"stage": stage, "candidate_id": candidate_id},
        },
    )
    assert response.status_code == 200
    return response.json()


def _finalize_stage(client: TestClient, task_id: str, stage: str) -> dict:
    response = client.post(
        f"/api/tasks/{task_id}/action",
        json={"action_type": "finalize_stage", "payload": {"stage": stage}},
    )
    assert response.status_code == 200
    return response.json()


def test_api_flow_scenario_entry(client: TestClient) -> None:
    response = client.post(
        "/api/tasks",
        json={"entry_point": "scenario", "scenario": "Test scenario"},
    )
    assert response.status_code == 200
    data = response.json()
    task_id = data["task"]["task_id"]
    artifact = data["current_stage_artifact"]

    for stage in ["driving_question", "question_chain", "activity", "experiment"]:
        assert _artifact_stage(artifact) == stage
        data = _select_first_candidate(client, task_id, stage, artifact)
        data = _finalize_stage(client, task_id, stage)
        artifact = data.get("current_stage_artifact")

    assert data["task"]["status"] == "completed"
    assert artifact is None


def test_api_flow_tool_seed_with_conflict_resolution(client: TestClient) -> None:
    tool_seed = {
        "tool_name": "Orange",
        "algorithms": ["KNN"],
        "affordances": ["classification"],
        "constraints": {"topic": "Test Topic", "grade": "G5", "duration": 45},
        "user_intent": "Teach classification",
    }
    response = client.post(
        "/api/tasks",
        json={"entry_point": "tool_seed", "tool_seed": tool_seed},
    )
    assert response.status_code == 200
    data = response.json()
    task_id = data["task"]["task_id"]
    artifact = data["current_stage_artifact"]

    for stage in ["scenario", "driving_question", "question_chain"]:
        assert _artifact_stage(artifact) == stage
        data = _select_first_candidate(client, task_id, stage, artifact)
        data = _finalize_stage(client, task_id, stage)
        artifact = data.get("current_stage_artifact")

    if _artifact_stage(artifact) == "activity":
        data = _select_first_candidate(client, task_id, "activity", artifact)
        artifact = data.get("current_stage_artifact")
        if _artifact_stage(artifact) == "activity":
            conflicts = data["task"]["conflicts"].get("activity", [])
            blocking = [
                c for c in conflicts if c["severity"] == "blocking" and not c.get("resolved", False)
            ]
            for conflict in blocking:
                response = client.post(
                    f"/api/tasks/{task_id}/action",
                    json={
                        "action_type": "resolve_conflict",
                        "payload": {
                            "stage": "activity",
                            "conflict_id": conflict["conflict_id"],
                            "option": "C",
                        },
                    },
                )
                assert response.status_code == 200
            data = _finalize_stage(client, task_id, "activity")
            artifact = data["current_stage_artifact"]

    assert _artifact_stage(artifact) == "experiment"

    data = _select_first_candidate(client, task_id, "experiment", artifact)
    data = _finalize_stage(client, task_id, "experiment")
    assert data["task"]["status"] == "completed"


def test_tool_seed_validation_error(client: TestClient) -> None:
    response = client.post(
        "/api/tasks",
        json={"entry_point": "tool_seed", "tool_seed": {"tool_name": "x"}},
    )
    assert response.status_code == 400


def test_llm_required_error(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_REQUIRED", "true")
    response = client.post(
        "/api/tasks",
        json={"entry_point": "scenario", "scenario": "Test scenario"},
    )
    assert response.status_code == 503


def test_chat_entry_ready(client: TestClient) -> None:
    response = client.post(
        "/api/chat",
        json={"message": "我想从场景开始", "session_id": None},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["task_id"]
