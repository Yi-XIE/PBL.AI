import pytest

from core.models import Candidate, StageArtifact, Task
from core.types import ActionType, CandidateStatus, EntryPoint, StageStatus, StageType
from engine.reducer import Event, apply_event
from services.orchestrator import Orchestrator
from services.sse_bus import SSEBus
from services.task_store import InMemoryTaskStore, JsonPersistence


def test_select_freezes_other_candidates() -> None:
    task = Task(
        entry_point=EntryPoint.scenario,
        entry_data={"scenario": "x"},
        current_stage=StageType.scenario,
    )
    artifact = StageArtifact(
        stage=StageType.scenario,
        candidates=[
            Candidate(id="A", title="A", status=CandidateStatus.generated, content={}),
            Candidate(id="B", title="B", status=CandidateStatus.generated, content={}),
        ],
    )
    task.artifacts[StageType.scenario] = artifact
    event = Event(
        type="candidate_selected",
        task_id=task.task_id,
        stage=StageType.scenario,
        payload={"candidate_id": "A"},
    )
    task = apply_event(task, event)
    statuses = {c.id: c.status for c in task.artifacts[StageType.scenario].candidates}
    assert statuses["A"] == CandidateStatus.selected
    assert statuses["B"] == CandidateStatus.frozen


def test_frozen_candidate_not_selectable(tmp_path) -> None:
    orch = Orchestrator(
        InMemoryTaskStore(),
        JsonPersistence(base_dir=str(tmp_path)),
        SSEBus(),
    )
    task = Task(
        entry_point=EntryPoint.scenario,
        entry_data={"scenario": "x"},
        current_stage=StageType.scenario,
    )
    artifact = StageArtifact(
        stage=StageType.scenario,
        status=StageStatus.pending_choice,
        candidates=[
            Candidate(id="A", title="A", status=CandidateStatus.selected, content={}),
            Candidate(id="B", title="B", status=CandidateStatus.frozen, content={}),
        ],
        selected_candidate_id="A",
    )
    task.artifacts[StageType.scenario] = artifact
    orch.store.save(task)
    with pytest.raises(ValueError):
        orch.apply_action(
            task.task_id,
            ActionType.select_candidate,
            {"stage": "scenario", "candidate_id": "B"},
        )
