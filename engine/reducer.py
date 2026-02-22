from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from core.models import Candidate, Conflict, DecisionResult, IntentRevision, Message, StageArtifact, Task, ToolSeed
from core.types import CandidateStatus, DialogueState, EntryPoint, StageStatus, StageType


class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    type: str
    task_id: str
    stage: Optional[StageType] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = Field(default_factory=dict)
    trace: Optional[Dict[str, Any]] = None


def _ensure_artifact(task: Task, stage: StageType) -> StageArtifact:
    if stage not in task.artifacts:
        task.artifacts[stage] = StageArtifact(stage=stage)
    return task.artifacts[stage]


def _normalize_candidates(items: List[Any]) -> List[Candidate]:
    normalized: List[Candidate] = []
    for item in items:
        if isinstance(item, Candidate):
            normalized.append(item)
        else:
            normalized.append(Candidate(**item))
    return normalized


def _freeze_candidates(candidates: List[Candidate]) -> List[Candidate]:
    frozen: List[Candidate] = []
    for cand in candidates:
        status = cand.status
        if status != CandidateStatus.selected:
            status = CandidateStatus.frozen
        frozen.append(cand.model_copy(update={"status": status}))
    return frozen


def _truncate(text: str, limit: int = 160) -> str:
    if not text:
        return ""
    cleaned = str(text).replace("\n", " ").strip()
    return cleaned[:limit]


def _summarize_candidate_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, dict):
        for key in ("scenario", "driving_question", "question_chain", "activity", "experiment"):
            if key in content:
                value = content.get(key)
                if isinstance(value, list):
                    return _truncate(" / ".join(str(item) for item in value[:3] if item))
                return _truncate(str(value))
        return _truncate(str(content))
    if isinstance(content, list):
        return _truncate(" / ".join(str(item) for item in content[:3] if item))
    return _truncate(str(content))


def _append_working_memory(task: Task, note: str, focus: Optional[str] = None) -> None:
    if note:
        task.working_memory.notes.append(_truncate(note, 200))
        task.working_memory.notes = task.working_memory.notes[-10:]
    if focus:
        task.working_memory.focus = focus


def apply_event(task: Task, event: Event) -> Task:
    task.updated_at = datetime.now(timezone.utc)

    if event.type == "task_created":
        entry_point = event.payload["entry_point"]
        if isinstance(entry_point, str):
            entry_point = EntryPoint(entry_point)
        task.entry_point = entry_point
        task.entry_data = event.payload.get("entry_data", {})
        tool_seed = event.payload.get("tool_seed")
        if tool_seed is not None and not isinstance(tool_seed, ToolSeed):
            if isinstance(tool_seed, dict):
                tool_seed = ToolSeed(**tool_seed)
        task.tool_seed = tool_seed
        current_stage = event.payload["current_stage"]
        if isinstance(current_stage, str):
            current_stage = StageType(current_stage)
        task.current_stage = current_stage
        completed = event.payload.get("completed_stages", [])
        task.completed_stages = [StageType(s) if isinstance(s, str) else s for s in completed]
        task.status = event.payload.get("status", "in_progress")
        task.stage_status = event.payload.get("stage_status", StageStatus.initialized)
        task.trace_root_id = event.payload.get("trace_root_id")
        return task

    if event.type == "decision_emitted":
        decision = event.payload.get("decision")
        if decision:
            task.last_decision = DecisionResult(**decision)
            task.decision_history.append(decision)
        return task

    if event.type in {"candidates_generated", "candidates_regenerated"}:
        if event.stage is None:
            return task
        artifact = _ensure_artifact(task, event.stage)
        if event.stage in task.conflicts:
            task.conflicts[event.stage] = []
        artifact.warnings = []
        revision_id = event.payload.get("revision_id")
        if revision_id and artifact.revision_id == revision_id:
            return task
        if artifact.candidates:
            artifact.history.append(
                {
                    "revision_id": artifact.revision_id,
                    "candidates": [c.model_dump() for c in _freeze_candidates(artifact.candidates)],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": event.type,
                }
            )
        artifact.revision_id = revision_id or uuid4().hex
        artifact.candidates = _normalize_candidates(event.payload.get("candidates", []))
        generation_context = event.payload.get("generation_context")
        if generation_context is None and artifact.candidates:
            generation_context = artifact.candidates[0].generation_context
        artifact.generation_context = generation_context or {}
        artifact.selected_candidate_id = None
        artifact.status = StageStatus.pending_choice
        if event.type == "candidates_regenerated":
            artifact.iteration_count += 1
        task.stage_status = artifact.status
        task.dialogue_state = DialogueState.selecting
        _append_working_memory(task, "", focus=f"select:{event.stage.value}")
        return task

    if event.type == "candidate_selected":
        if event.stage is None:
            return task
        artifact = _ensure_artifact(task, event.stage)
        if event.stage in task.conflicts:
            task.conflicts[event.stage] = []
        selected_id = event.payload.get("candidate_id")
        artifact.selected_candidate_id = selected_id
        updated: List[Candidate] = []
        for cand in artifact.candidates:
            if cand.id == selected_id:
                updated.append(cand.model_copy(update={"status": CandidateStatus.selected}))
            else:
                updated.append(cand.model_copy(update={"status": CandidateStatus.frozen}))
        artifact.candidates = updated
        task.stage_status = artifact.status
        if selected_id:
            task.decision_history.append(
                {"type": "candidate_selected", "stage": event.stage.value, "candidate_id": selected_id}
            )
            selected = next((c for c in artifact.candidates if c.id == selected_id), None)
            note = _summarize_candidate_content(selected.content) if selected else ""
            _append_working_memory(task, f"selected {event.stage.value}: {note}", focus=f"selected:{event.stage.value}")
        return task

    if event.type == "feedback_recorded":
        if event.stage is None:
            return task
        artifact = _ensure_artifact(task, event.stage)
        artifact.status = StageStatus.feedback_loop
        task.dialogue_state = DialogueState.generating
        artifact.history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reason": "feedback",
                "feedback": event.payload.get("feedback", ""),
            }
        )
        task.stage_status = artifact.status
        feedback_text = event.payload.get("feedback", "")
        _append_working_memory(task, f"feedback {event.stage.value}: {feedback_text}", focus=f"feedback:{event.stage.value}")
        return task

    if event.type == "conflict_detected":
        if event.stage is None:
            return task
        conflicts = task.conflicts.get(event.stage, [])
        conflict = Conflict(**event.payload["conflict"])
        conflicts.append(conflict)
        task.conflicts[event.stage] = conflicts
        task.dialogue_state = DialogueState.conflict_resolution
        _append_working_memory(task, "", focus=f"conflict:{event.stage.value}")
        return task

    if event.type == "conflict_resolved":
        if event.stage is None:
            return task
        conflicts = task.conflicts.get(event.stage, [])
        conflict_id = event.payload.get("conflict_id")
        resolved_option = event.payload.get("option")
        updated: List[Conflict] = []
        for conflict in conflicts:
            if conflict.conflict_id == conflict_id:
                updated.append(
                    conflict.model_copy(
                        update={"resolved": True, "resolved_option": resolved_option}
                    )
                )
            else:
                updated.append(conflict)
        task.conflicts[event.stage] = updated
        task.dialogue_state = DialogueState.selecting
        task.decision_history.append(
            {
                "type": "conflict_resolved",
                "stage": event.stage.value,
                "conflict_id": conflict_id,
                "option": resolved_option,
            }
        )
        _append_working_memory(task, "", focus=f"select:{event.stage.value}")
        return task

    if event.type == "message_emitted":
        payload = event.payload.get("message") if event.payload else None
        if payload:
            message = Message(**payload)
            task.messages.append(message)
            if message.kind == "entry_decision" and message.entry_decision is not None:
                task.decision_history.append(
                    {
                        "type": "entry_decision",
                        "chosen_entry_point": message.entry_decision.chosen_entry_point.value,
                        "rules_hit": message.entry_decision.rules_hit,
                        "confidence": message.entry_decision.confidence,
                    }
                )
        return task

    if event.type == "intent_updated":
        payload = event.payload or {}
        after = payload.get("after")
        before = payload.get("before")
        revision = payload.get("revision")
        if isinstance(after, str) and after.strip():
            task.creative_context.original_intent = after.strip()
            if after.strip() not in task.creative_context.anchor_concepts:
                task.creative_context.anchor_concepts.append(after.strip())
        if isinstance(revision, dict):
            task.creative_context.intent_evolution.append(IntentRevision(**revision))
        task.decision_history.append(
            {"type": "intent_updated", "before": before, "after": after}
        )
        return task

    if event.type == "stage_finalized":
        if event.stage is None:
            return task
        artifact = _ensure_artifact(task, event.stage)
        artifact.status = StageStatus.finalized
        task.stage_status = StageStatus.finalized
        task.dialogue_state = DialogueState.generating
        if event.stage not in task.completed_stages:
            task.completed_stages.append(event.stage)
        next_stage = event.payload.get("next_stage")
        if isinstance(next_stage, str):
            next_stage = StageType(next_stage)
        if next_stage is not None:
            task.current_stage = next_stage
            _append_working_memory(task, "", focus=f"stage:{next_stage.value}")
        else:
            _append_working_memory(task, "", focus="stage:completed")
        return task

    if event.type == "stage_redirected":
        target = event.payload.get("current_stage") or event.stage
        if isinstance(target, str):
            target = StageType(target)
        if isinstance(target, StageType):
            task.current_stage = target
            task.stage_status = StageStatus.initialized
            task.decision_history.append(
                {"type": "require_previous", "stage": target.value}
            )
            _append_working_memory(task, "", focus=f"stage:{target.value}")
        return task

    if event.type == "task_completed":
        task.status = "completed"
        return task

    if event.type == "error_raised":
        task.status = "error"
        return task

    return task
