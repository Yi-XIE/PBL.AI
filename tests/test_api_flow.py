import json
import time
import pytest
from typing import Optional
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from api.app import app
import api.routes.tasks as tasks_module
from services.orchestrator import Orchestrator
from services.sse_bus import SSEBus
from services.task_store import InMemoryTaskStore, JsonPersistence


class FakeChatModel(Runnable):
    _global_index = 0

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
        if "entry_point" in text and "confidence" in text and "reason" in text:
            payload = '{"entry_point":"scenario","confidence":0.8,"reason":"rule_match"}'
            return AIMessage(content=payload)
        FakeChatModel._global_index += 1
        suffix = FakeChatModel._global_index
        themes = [
            "Ocean cleanup",
            "Smart campus",
            "Community health",
            "Space exploration",
            "Forest conservation",
            "City traffic",
        ]
        theme = themes[suffix % len(themes)]
        options = []
        for idx in range(3):
            letter = chr(65 + idx)
            options.append(
                {
                    "title": f"{theme} Option {letter}",
                    "scenario": f"{theme} scenario {letter}: plan {suffix}",
                    "driving_question": f"How can we address {theme.lower()} in option {letter}?",
                    "question_chain": [
                        f"{theme} sub-question {letter}-1",
                        f"{theme} sub-question {letter}-2",
                        f"{theme} sub-question {letter}-3",
                    ],
                    "activity": (
                        f"### {theme} Activity {letter}\n"
                        f"子问题1：{theme} quick intuition check\n"
                        f"活动1：students make a quick choice and justify.\n"
                        f"子问题2：{theme} counterexample / boundary\n"
                        f"活动2：use data to show intuition can be wrong.\n"
                        f"子问题3：{theme} method + evidence + transfer\n"
                        f"活动3：build a simple method and test transfer.\n"
                    ),
                    "experiment": f"### {theme} Experiment {letter}\n- Hypothesis for {theme.lower()}\n- Test scenario {suffix}",
                }
            )
        return AIMessage(content=json.dumps({"options": options}, ensure_ascii=False))


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


def _wait_for_artifact(client: TestClient, task_id: str, stage: str, timeout: float = 3.0) -> Optional[dict]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/tasks/{task_id}")
        if response.status_code != 200:
            time.sleep(0.05)
            continue
        data = response.json()
        artifact = (data.get("artifacts") or {}).get(stage)
        if artifact and artifact.get("candidates"):
            return artifact
        time.sleep(0.05)
    return None


def _ensure_current_artifact(client: TestClient, task_id: str, data: dict) -> Optional[dict]:
    artifact = data.get("current_stage_artifact")
    if artifact:
        return artifact
    stage = data.get("task", {}).get("current_stage")
    if stage:
        return _wait_for_artifact(client, task_id, stage)
    return None


def test_api_flow_scenario_entry(client: TestClient) -> None:
    response = client.post(
        "/api/tasks",
        json={"entry_point": "scenario", "scenario": "Test scenario"},
    )
    assert response.status_code == 200
    data = response.json()
    task_id = data["task"]["task_id"]
    artifact = data["current_stage_artifact"]

    for stage in ["scenario", "driving_question", "question_chain", "activity", "experiment"]:
        assert _artifact_stage(artifact) == stage
        data = _select_first_candidate(client, task_id, stage, artifact)
        artifact = _ensure_current_artifact(client, task_id, data)

    assert data["task"]["status"] == "completed"
    if artifact is not None:
        assert _artifact_stage(artifact) == "experiment"


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
        artifact = _ensure_current_artifact(client, task_id, data)

    if _artifact_stage(artifact) == "activity":
        data = _select_first_candidate(client, task_id, "activity", artifact)
        artifact = _ensure_current_artifact(client, task_id, data)
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
                data = response.json()
            artifact = _ensure_current_artifact(client, task_id, data)

    assert _artifact_stage(artifact) == "experiment"

    data = _select_first_candidate(client, task_id, "experiment", artifact)
    assert data["task"]["status"] == "completed"


def test_feedback_regenerates_candidates(client: TestClient) -> None:
    response = client.post(
        "/api/tasks",
        json={"entry_point": "scenario", "scenario": "Test scenario"},
    )
    assert response.status_code == 200
    data = response.json()
    task_id = data["task"]["task_id"]
    artifact = data["current_stage_artifact"]
    assert _artifact_stage(artifact) == "scenario"
    iteration_before = artifact["iteration_count"]

    response = client.post(
        f"/api/tasks/{task_id}/action",
        json={
            "action_type": "provide_feedback",
            "payload": {"stage": "scenario", "feedback": "Add more detail."},
        },
    )
    assert response.status_code == 200
    data = response.json()
    artifact = data["current_stage_artifact"]
    assert _artifact_stage(artifact) == "scenario"
    assert artifact["iteration_count"] == iteration_before + 1


def test_tool_seed_validation_error(client: TestClient) -> None:
    response = client.post(
        "/api/tasks",
        json={"entry_point": "tool_seed", "tool_seed": {"tool_name": "x"}},
    )
    assert response.status_code == 400


def test_llm_required_error(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("LLM_REQUIRED", "true")
    response = client.post(
        "/api/tasks",
        json={"entry_point": "scenario", "scenario": "Test scenario"},
    )
    assert response.status_code == 503


def test_chat_entry_ready(client: TestClient) -> None:
    response = client.post(
        "/api/chat",
        json={"message": "Start from scenario", "session_id": None},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["task_id"]

    task_id = data["task_id"]
    task_response = client.get(f"/api/tasks/{task_id}")
    assert task_response.status_code == 200
    task = task_response.json()
    assert any(msg.get("entry_decision") for msg in task.get("messages", []))
