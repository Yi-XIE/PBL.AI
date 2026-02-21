from core.types import ActionType, EntryPoint
from engine.state_machine import MAX_ITERATIONS
from services.orchestrator import Orchestrator
from services.sse_bus import SSEBus
from services.task_store import InMemoryTaskStore, JsonPersistence


def test_regenerate_limit_force_exit(tmp_path) -> None:
    orch = Orchestrator(
        InMemoryTaskStore(),
        JsonPersistence(base_dir=str(tmp_path)),
        SSEBus(),
    )
    task, _, artifact = orch.create_task(EntryPoint.scenario, {"scenario": "x"})
    stage = artifact.stage if artifact else task.current_stage
    for _ in range(MAX_ITERATIONS):
        task, decision, _ = orch.apply_action(
            task.task_id,
            ActionType.regenerate_candidates,
            {"stage": stage.value},
        )
        assert decision.direction != "force_exit"
    _, decision, _ = orch.apply_action(
        task.task_id,
        ActionType.regenerate_candidates,
        {"stage": stage.value},
    )
    assert decision.direction == "force_exit"
    assert decision.constraints.get("recommended_candidate_id") is not None
