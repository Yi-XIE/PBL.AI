import pytest
from fastapi.testclient import TestClient

from api.app import app
import api.routes.tasks as tasks_module
from services.orchestrator import Orchestrator
from services.sse_bus import SSEBus
from services.task_store import InMemoryTaskStore, JsonPersistence


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

            response = client.post(
                f"/api/tasks/{task_id}/action",
                json={"action_type": "finalize_stage", "payload": {"stage": "activity"}},
            )
            assert response.status_code == 200
            data = response.json()
            artifact = data["current_stage_artifact"]

    assert _artifact_stage(artifact) == "experiment"

    data = _select_first_candidate(client, task_id, "experiment", artifact)
    assert data["task"]["status"] == "completed"


def test_tool_seed_validation_error(client: TestClient) -> None:
    response = client.post(
        "/api/tasks",
        json={"entry_point": "tool_seed", "tool_seed": {"tool_name": "x"}},
    )
    assert response.status_code == 400
