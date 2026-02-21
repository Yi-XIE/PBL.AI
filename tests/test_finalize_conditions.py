from core.models import Candidate, Conflict, StageArtifact, Task
from core.types import CandidateStatus, ConflictSeverity, EntryPoint, StageType
from services.orchestrator import Orchestrator
from services.sse_bus import SSEBus
from services.task_store import InMemoryTaskStore, JsonPersistence


def _orchestrator(tmp_path) -> Orchestrator:
    return Orchestrator(
        InMemoryTaskStore(),
        JsonPersistence(base_dir=str(tmp_path)),
        SSEBus(),
    )


def test_finalize_requires_selected_candidate(tmp_path) -> None:
    orch = _orchestrator(tmp_path)
    task = Task(
        entry_point=EntryPoint.scenario,
        entry_data={"scenario": "x"},
        current_stage=StageType.scenario,
    )
    candidate = Candidate(
        id="A",
        title="A",
        status=CandidateStatus.generated,
        content={"scenario": "x"},
    )
    artifact = StageArtifact(stage=StageType.scenario, candidates=[candidate])
    task.artifacts[StageType.scenario] = artifact
    assert orch._can_finalize(task, StageType.scenario) is False

    artifact.selected_candidate_id = "A"
    assert orch._can_finalize(task, StageType.scenario) is False

    artifact.candidates = [
        artifact.candidates[0].model_copy(update={"status": CandidateStatus.selected})
    ]
    conflict = Conflict(
        stage=StageType.scenario,
        severity=ConflictSeverity.blocking,
        summary="blocking",
    )
    task.conflicts[StageType.scenario] = [conflict]
    assert orch._can_finalize(task, StageType.scenario) is False
