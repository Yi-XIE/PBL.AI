from core.types import ActionType, EntryPoint
from services.orchestrator import Orchestrator
from services.sse_bus import SSEBus
from services.task_store import InMemoryTaskStore, JsonPersistence


def test_task_and_event_persistence(tmp_path) -> None:
    persistence = JsonPersistence(base_dir=str(tmp_path))
    orch = Orchestrator(InMemoryTaskStore(), persistence, SSEBus())

    task, _, artifact = orch.create_task(EntryPoint.scenario, {"scenario": "x"})
    stage = artifact.stage if artifact else task.current_stage
    first_candidate_id = artifact.candidates[0].id if artifact else None
    assert first_candidate_id is not None

    orch.apply_action(
        task.task_id,
        ActionType.select_candidate,
        {"stage": stage.value, "candidate_id": first_candidate_id},
    )

    events_path = tmp_path / "events" / f"{task.task_id}.jsonl"
    assert events_path.exists()
    lines = events_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2
    joined = "\n".join(lines)
    assert "\"task_created\"" in joined
    assert "\"candidates_generated\"" in joined
    assert "\"candidate_selected\"" in joined
