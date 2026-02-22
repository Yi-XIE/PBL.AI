from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from adapters.tracing import TraceManager
from core.dependencies import STAGE_SEQUENCE
from core.models import Candidate, DecisionResult, Explanation, Message, StageArtifact, Task, ToolSeed
from core.types import ActionType, CandidateStatus, ConflictSeverity, EntryPoint, StageStatus, StageType
from engine.decision import make_decision, next_required_stage
from engine.flow_nodes import (
    candidate_stage_node,
    dependency_check_node,
    entry_node,
    require_previous_stage,
    stage_finalize_node,
    user_choice_gate,
)
from engine.reducer import Event, apply_event
from engine.state_machine import MAX_ITERATIONS, can_apply_action, should_force_exit
from generators.registry import GENERATOR_BY_STAGE
from services.sse_bus import SSEBus
from services.task_store import InMemoryTaskStore, JsonPersistence
from utils.serialization import to_jsonable
from validators.activity_alignment import validate_activity_alignment
from validators.simple import validate_non_empty
from services.decision_messenger import build_decision_message


class Orchestrator:
    def __init__(
        self,
        store: InMemoryTaskStore,
        persistence: JsonPersistence,
        sse_bus: SSEBus,
        tracer: Optional[TraceManager] = None,
    ) -> None:
        self.store = store
        self.persistence = persistence
        self.sse_bus = sse_bus
        self.tracer = tracer or TraceManager()
        self.timeout_seconds = self._load_timeout()

    def _load_timeout(self) -> int:
        value = os.getenv("USER_ACTION_TIMEOUT_SECONDS", "3600")
        try:
            return max(0, int(value))
        except ValueError:
            return 0

    def _normalize_stage(self, stage_value: Any, fallback: StageType) -> StageType:
        if isinstance(stage_value, StageType):
            return stage_value
        if stage_value is None:
            return fallback
        return StageType(stage_value)

    def _maybe_emit_timeout(self, task: Task) -> None:
        if self.timeout_seconds <= 0:
            return
        if task.stage_status not in {StageStatus.pending_choice, StageStatus.feedback_loop}:
            return
        age_seconds = (datetime.now(timezone.utc) - task.updated_at).total_seconds()
        if age_seconds < self.timeout_seconds:
            return
        self._publish(
            task.task_id,
            "message",
            {
                "role": "system",
                "text": "No selection for a while. You can resume by selecting a candidate or regenerating.",
            },
            stage=task.current_stage,
            timestamp=datetime.now(timezone.utc),
            trace={"run_id": task.trace_root_id},
        )

    def _recommend_candidate(self, artifact: Optional[StageArtifact]) -> Optional[Candidate]:
        if artifact is None or not artifact.candidates:
            return None
        best: Optional[Candidate] = None
        for candidate in artifact.candidates:
            if best is None or candidate.alignment_score > best.alignment_score:
                best = candidate
        return best

    def _trace_flow(self, task: Task, name: str, payload: Dict[str, Any]) -> None:
        stage_value = payload.get("stage") if isinstance(payload, dict) else None
        if isinstance(stage_value, StageType):
            stage_value = stage_value.value
        if not stage_value:
            stage_value = task.current_stage.value
        self.tracer.log_child(
            root_run_id=task.trace_root_id,
            name=f"flow:{name}",
            run_type="chain",
            inputs=payload,
            outputs={},
            metadata={"task_id": task.task_id, "stage": stage_value, "action": f"flow:{name}"},
        )

    def create_task(
        self,
        entry_point: EntryPoint,
        entry_data: Dict[str, Any],
    ) -> Tuple[Task, DecisionResult, Optional[StageArtifact]]:
        completed_stages = [StageType.tool_seed] if entry_point == EntryPoint.tool_seed else []
        task = Task(
            entry_point=entry_point,
            entry_data=entry_data,
            tool_seed=ToolSeed(**entry_data) if entry_point == EntryPoint.tool_seed else None,
            current_stage=StageType.scenario,
            completed_stages=completed_stages,
            artifacts={},
        )

        trace_root_id = self.tracer.start_root(
            task.task_id,
            entry_point.value,
            task.current_stage.value,
            action="task_created",
        )
        try:
            task_created_event = Event(
                type="task_created",
                task_id=task.task_id,
                stage=None,
                payload={
                    "entry_point": entry_point,
                    "entry_data": entry_data,
                    "tool_seed": task.tool_seed,
                    "current_stage": task.current_stage,
                    "completed_stages": task.completed_stages,
                    "status": task.status,
                    "stage_status": task.stage_status,
                    "trace_root_id": trace_root_id,
                },
            )
            task = self._emit_event(task, task_created_event, sse_event="task_updated")
            self._trace_flow(task, "entry", entry_node(task))

            decision_target = next_required_stage(task) or task.current_stage
            decision = make_decision(task, target_stage=decision_target, requested_action="create_task")
            task = self._emit_decision(task, decision)

            current_artifact: Optional[StageArtifact] = None
            if decision.direction == "forward" and decision.next_stage:
                command = candidate_stage_node(task, decision.next_stage)
                self._trace_flow(
                    task,
                    "candidate_stage",
                    {"stage": command.stage.value, "count": command.count},
                )
                candidates = self._generate_candidates(task, command.stage, feedback=None, count=command.count)
                task, current_artifact = self._apply_candidates(
                    task,
                    command.stage,
                    candidates,
                    regenerate=False,
                )
                self._run_validators(task, command.stage, candidates)

            self.tracer.log_child(
                root_run_id=task.trace_root_id,
                name="api:create_task",
                run_type="chain",
                inputs={"entry_point": entry_point.value},
                outputs={"task_id": task.task_id},
                metadata={"task_id": task.task_id, "stage": task.current_stage.value, "action": "create_task"},
            )
            return task, decision, current_artifact
        except Exception as exc:
            self.tracer.log_child(
                root_run_id=trace_root_id,
                name="api:create_task:error",
                run_type="chain",
                inputs={"entry_point": entry_point.value},
                outputs={},
                metadata={"task_id": task.task_id, "stage": task.current_stage.value, "action": "create_task"},
                error=str(exc),
            )
            if not isinstance(exc, ValueError):
                try:
                    self._emit_event(
                        task,
                        Event(
                            type="error_raised",
                            task_id=task.task_id,
                            stage=task.current_stage,
                            payload={"message": str(exc)},
                        ),
                        sse_event="error",
                        sse_payload={"code": "internal_error", "message": str(exc)},
                    )
                except Exception:
                    pass
            raise

    def apply_action(
        self,
        task_id: str,
        action_type: ActionType,
        payload: Dict[str, Any],
    ) -> Tuple[Task, DecisionResult, Optional[StageArtifact]]:
        task = self.store.get(task_id)
        if not task:
            raise ValueError("Task not found")

        self._maybe_emit_timeout(task)
        stage = self._normalize_stage(payload.get("stage"), task.current_stage)
        self.tracer.log_child(
            root_run_id=task.trace_root_id,
            name=f"api:action:{action_type.value}",
            run_type="chain",
            inputs={"stage": stage.value, "payload": payload},
            outputs={},
            metadata={"task_id": task.task_id, "stage": stage.value, "action": action_type.value},
        )
        try:
            artifact = task.artifacts.get(stage)
            if artifact and not can_apply_action(artifact.status, action_type):
                raise ValueError("Action not allowed in current stage status")

            flow_check = dependency_check_node(task, stage)
            self._trace_flow(
                task,
                "dependency_check",
                {
                    "stage": stage.value,
                    "can_proceed": flow_check.get("can_proceed"),
                    "missing": [s.value for s in flow_check.get("missing", [])],
                },
            )
            if flow_check.get("error"):
                decision = DecisionResult(
                    next_stage=None,
                    direction="error",
                    explanation=Explanation(summary=flow_check["error"], details=[]),
                    user_message="Dependency cycle detected. Please review the dependency table.",
                    constraints={"error": "dependency_cycle"},
                )
                task = self._emit_decision(task, decision)
                task = self._emit_event(
                    task,
                    Event(
                        type="error_raised",
                        task_id=task.task_id,
                        stage=stage,
                        payload={"message": flow_check["error"]},
                    ),
                    sse_event="error",
                    sse_payload={"code": "dependency_cycle", "message": flow_check["error"]},
                )
                return task, decision, task.artifacts.get(stage)

            missing_chain = flow_check.get("missing", [])
            if missing_chain and missing_chain[0] != stage:
                decision = require_previous_stage(task, missing_chain)
                task = self._emit_decision(task, decision)
                task = self._emit_event(
                    task,
                    Event(
                        type="stage_redirected",
                        task_id=task.task_id,
                        stage=missing_chain[0],
                        payload={"current_stage": missing_chain[0]},
                    ),
                    sse_event="task_updated",
                )
                return task, decision, task.artifacts.get(missing_chain[0])

            if action_type == ActionType.provide_feedback:
                feedback = payload.get("feedback", "")
                task = self._emit_event(
                    task,
                    Event(
                        type="feedback_recorded",
                        task_id=task.task_id,
                        stage=stage,
                        payload={"feedback": feedback},
                    ),
                    sse_event="message",
                    sse_payload={"role": "system", "text": "Feedback recorded."},
                )

                if artifact and should_force_exit(artifact.iteration_count):
                    recommended = self._recommend_candidate(artifact)
                    constraints = {"force_exit": True}
                    details = [f"MAX_ITERATIONS={MAX_ITERATIONS}"]
                    user_message = "Iteration limit reached. Please select a candidate to proceed."
                    if recommended:
                        constraints.update(
                            {
                                "recommended_candidate_id": recommended.id,
                                "recommended_title": recommended.title,
                                "recommended_alignment_score": recommended.alignment_score,
                            }
                        )
                        details.append(f"Recommended: {recommended.id} - {recommended.title}")
                        user_message = (
                            "Iteration limit reached. Recommended candidate "
                            f"{recommended.id}: {recommended.title}. Please confirm selection."
                        )
                    decision = DecisionResult(
                        next_stage=stage,
                        direction="force_exit",
                        explanation=Explanation(
                            summary="Maximum iterations reached.",
                            details=details,
                        ),
                        user_message=user_message,
                        constraints=constraints,
                    )
                    task = self._emit_decision(task, decision)
                    return task, decision, artifact

                command = candidate_stage_node(task, stage)
                self._trace_flow(
                    task,
                    "candidate_stage",
                    {"stage": command.stage.value, "count": command.count},
                )
                candidates = self._generate_candidates(
                    task,
                    command.stage,
                    feedback=feedback,
                    count=command.count,
                )
                task, current_artifact = self._apply_candidates(
                    task,
                    command.stage,
                    candidates,
                    regenerate=True,
                )
                self._run_validators(task, command.stage, candidates)
                decision = make_decision(task, target_stage=stage, requested_action=action_type.value)
                task = self._emit_decision(task, decision)
                return task, decision, current_artifact

            if action_type == ActionType.regenerate_candidates:
                if artifact and should_force_exit(artifact.iteration_count):
                    recommended = self._recommend_candidate(artifact)
                    constraints = {"force_exit": True}
                    details = [f"MAX_ITERATIONS={MAX_ITERATIONS}"]
                    user_message = "Iteration limit reached. Please select a candidate to proceed."
                    if recommended:
                        constraints.update(
                            {
                                "recommended_candidate_id": recommended.id,
                                "recommended_title": recommended.title,
                                "recommended_alignment_score": recommended.alignment_score,
                            }
                        )
                        details.append(f"Recommended: {recommended.id} - {recommended.title}")
                        user_message = (
                            "Iteration limit reached. Recommended candidate "
                            f"{recommended.id}: {recommended.title}. Please confirm selection."
                        )
                    decision = DecisionResult(
                        next_stage=stage,
                        direction="force_exit",
                        explanation=Explanation(
                            summary="Maximum iterations reached.",
                            details=details,
                        ),
                        user_message=user_message,
                        constraints=constraints,
                    )
                    task = self._emit_decision(task, decision)
                    return task, decision, artifact

                command = candidate_stage_node(task, stage)
                self._trace_flow(
                    task,
                    "candidate_stage",
                    {"stage": command.stage.value, "count": command.count},
                )
                candidates = self._generate_candidates(
                    task,
                    command.stage,
                    feedback=payload.get("feedback"),
                    count=command.count,
                )
                task, current_artifact = self._apply_candidates(task, command.stage, candidates, regenerate=True)
                self._run_validators(task, command.stage, candidates)
                decision = make_decision(task, target_stage=stage, requested_action=action_type.value)
                task = self._emit_decision(task, decision)
                return task, decision, current_artifact

            if action_type == ActionType.select_candidate:
                if not artifact:
                    raise ValueError("No candidates to select")
                candidate_id = payload.get("candidate_id")
                candidate = next((c for c in artifact.candidates if c.id == candidate_id), None)
                if not candidate or candidate.status == CandidateStatus.frozen:
                    raise ValueError("Candidate not selectable")
                self._trace_flow(task, "user_choice_gate", user_choice_gate(task, action_type.value))
                task = self._emit_event(
                    task,
                    Event(
                        type="candidate_selected",
                        task_id=task.task_id,
                        stage=stage,
                        payload={"candidate_id": candidate_id},
                    ),
                    sse_event="task_updated",
                )
                self._run_validators(task, stage, artifact.candidates)
                if not self._can_finalize(task, stage):
                    blocking = [
                        c for c in task.conflicts.get(stage, [])
                        if c.severity == ConflictSeverity.blocking and not c.resolved
                    ]
                    decision = DecisionResult(
                        next_stage=stage,
                        direction="stay",
                        explanation=Explanation(
                            summary="Finalize conditions not met.",
                            details=["Resolve blocking conflicts before moving on."],
                        ),
                        user_message="Selection saved. Resolve blocking conflicts to proceed.",
                    )
                    task = self._emit_decision(task, decision)
                    if blocking:
                        conflict = blocking[0]
                        options_text = " | ".join(
                            [
                                f"{opt.option}:{opt.title}"
                                for opt in conflict.conflict_options
                            ]
                        )
                        message_text = (
                            f"Blocking conflict: {conflict.summary}. "
                            f"Options: {options_text}. Reply with option letter to resolve."
                        )
                        message = Message(
                            role="assistant",
                            text=message_text,
                            stage=stage,
                            kind="conflict",
                        )
                        task = self._emit_event(
                            task,
                            Event(
                                type="message_emitted",
                                task_id=task.task_id,
                                stage=stage,
                                payload={"message": message.model_dump()},
                            ),
                            sse_event="message",
                            sse_payload={
                                "role": message.role,
                                "text": message.text,
                                "stage": message.stage.value if message.stage else None,
                            },
                        )
                    return task, decision, task.artifacts.get(stage)

                task = self._finalize_stage(task, stage)
                decision = make_decision(
                    task,
                    target_stage=task.current_stage,
                    requested_action="auto_finalize_after_select",
                )
                task = self._emit_decision(task, decision)
                current_artifact = None
                if decision.direction == "forward" and decision.next_stage:
                    command = candidate_stage_node(task, decision.next_stage)
                    self._trace_flow(
                        task,
                        "candidate_stage",
                        {"stage": command.stage.value, "count": command.count},
                    )
                    self._schedule_candidates(
                        task.task_id,
                        command.stage,
                        feedback=None,
                        count=command.count,
                        regenerate=False,
                    )
                return task, decision, current_artifact

            if action_type == ActionType.finalize_stage:
                if not self._can_finalize(task, stage):
                    decision = DecisionResult(
                        next_stage=stage,
                        direction="stay",
                        explanation=Explanation(
                            summary="Finalize conditions not met.",
                            details=["Select a candidate and resolve blocking conflicts before finalizing."],
                        ),
                        user_message="Finalize conditions not met.",
                    )
                    task = self._emit_decision(task, decision)
                    return task, decision, task.artifacts.get(stage)
                task = self._finalize_stage(task, stage)
                decision = make_decision(task, target_stage=task.current_stage, requested_action=action_type.value)
                task = self._emit_decision(task, decision)
                current_artifact = None
                if decision.direction == "forward" and decision.next_stage:
                    command = candidate_stage_node(task, decision.next_stage)
                    self._trace_flow(
                        task,
                        "candidate_stage",
                        {"stage": command.stage.value, "count": command.count},
                    )
                    self._schedule_candidates(
                        task.task_id,
                        command.stage,
                        feedback=None,
                        count=command.count,
                        regenerate=False,
                    )
                return task, decision, current_artifact

            if action_type == ActionType.resolve_conflict:
                conflict_id = payload.get("conflict_id")
                option = payload.get("option")
                if not conflict_id:
                    conflicts = task.conflicts.get(stage, [])
                    conflict_id = conflicts[-1].conflict_id if conflicts else None
                if not conflict_id or not option:
                    raise ValueError("conflict_id and option are required to resolve conflicts")
                task = self._emit_event(
                    task,
                    Event(
                        type="conflict_resolved",
                        task_id=task.task_id,
                        stage=stage,
                        payload={"conflict_id": conflict_id, "option": option},
                    ),
                    sse_event="task_updated",
                )
                if self._can_finalize(task, stage):
                    task = self._finalize_stage(task, stage)
                    decision = make_decision(
                        task,
                        target_stage=task.current_stage,
                        requested_action="auto_finalize_after_conflict",
                    )
                    task = self._emit_decision(task, decision)
                    current_artifact = None
                    if decision.direction == "forward" and decision.next_stage:
                        command = candidate_stage_node(task, decision.next_stage)
                        self._trace_flow(
                            task,
                            "candidate_stage",
                            {"stage": command.stage.value, "count": command.count},
                        )
                        self._schedule_candidates(
                            task.task_id,
                            command.stage,
                            feedback=None,
                            count=command.count,
                            regenerate=False,
                        )
                    return task, decision, current_artifact
                decision = make_decision(task, target_stage=stage, requested_action=action_type.value)
                task = self._emit_decision(task, decision)
                return task, decision, task.artifacts.get(stage)

            raise ValueError("Unsupported action type")
        except Exception as exc:
            self.tracer.log_child(
                root_run_id=task.trace_root_id,
                name="api:action:error",
                run_type="chain",
                inputs={"stage": stage.value, "payload": payload, "action": action_type.value},
                outputs={},
                metadata={"task_id": task.task_id, "stage": stage.value, "action": action_type.value},
                error=str(exc),
            )
            if not isinstance(exc, ValueError):
                try:
                    self._emit_event(
                        task,
                        Event(
                            type="error_raised",
                            task_id=task.task_id,
                            stage=stage,
                            payload={"message": str(exc)},
                        ),
                        sse_event="error",
                        sse_payload={"code": "internal_error", "message": str(exc)},
                    )
                except Exception:
                    pass
            raise

    def _bootstrap_scenario_from_entry(self, task: Task, entry_data: Dict[str, Any]) -> None:
        scenario_text = entry_data.get("scenario")
        if isinstance(scenario_text, dict):
            scenario_text = scenario_text.get("scenario", "")
        candidate = Candidate(
            id="A",
            title="Provided Scenario",
            status=CandidateStatus.selected,
            content={"scenario": scenario_text or ""},
            rationale="",
            derived_from=["entry_point"],
            alignment_score=1.0,
            generation_context={
                "based_on": ["entry_point"],
                "constraints_applied": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        task, _ = self._apply_candidates(task, StageType.scenario, [candidate], regenerate=False)
        task = self._emit_event(
            task,
            Event(
                type="candidate_selected",
                task_id=task.task_id,
                stage=StageType.scenario,
                payload={"candidate_id": "A"},
            ),
            sse_event="task_updated",
        )
        task = self._finalize_stage(task, StageType.scenario)

    def _finalize_stage(self, task: Task, stage: StageType) -> Task:
        self._trace_flow(task, "stage_finalize", stage_finalize_node(task))
        next_stage = self._compute_next_stage(task, stage)
        task = self._emit_event(
            task,
            Event(
                type="stage_finalized",
                task_id=task.task_id,
                stage=stage,
                payload={"next_stage": next_stage},
            ),
            sse_event="task_updated",
        )
        if next_stage is None:
            task = self._emit_event(
                task,
                Event(type="task_completed", task_id=task.task_id, stage=stage, payload={}),
                sse_event="task_updated",
            )
        return task

    def _compute_next_stage(self, task: Task, stage: StageType) -> Optional[StageType]:
        sequence = [s for s in STAGE_SEQUENCE]
        if stage not in sequence:
            return None
        index = sequence.index(stage) + 1
        while index < len(sequence):
            next_stage = sequence[index]
            if next_stage not in task.completed_stages:
                return next_stage
            index += 1
        return None

    def _can_finalize(self, task: Task, stage: StageType) -> bool:
        artifact = task.artifacts.get(stage)
        if not artifact or not artifact.selected_candidate_id:
            return False
        selected = next((c for c in artifact.candidates if c.id == artifact.selected_candidate_id), None)
        if not selected or selected.status != CandidateStatus.selected:
            return False
        conflicts = task.conflicts.get(stage, [])
        for conflict in conflicts:
            if conflict.severity == ConflictSeverity.blocking and not conflict.resolved:
                return False
        return True

    def _generate_candidates(
        self,
        task: Task,
        stage: StageType,
        feedback: Optional[str],
        count: int = 3,
    ) -> List[Candidate]:
        generator = GENERATOR_BY_STAGE.get(stage)
        if generator is None:
            raise ValueError("No generator for stage")

        start_time = datetime.now(timezone.utc)
        candidates = generator.generate(task, count=count, feedback=feedback)
        end_time = datetime.now(timezone.utc)
        self.tracer.log_child(
            root_run_id=task.trace_root_id,
            name=f"generator:{stage.value}",
            run_type="tool",
            inputs={"stage": stage.value, "feedback": feedback or ""},
            outputs={"count": len(candidates)},
            metadata={"task_id": task.task_id, "stage": stage.value, "action": "generate_candidates"},
            start_time=start_time,
            end_time=end_time,
        )
        return candidates

    def _schedule_candidates(
        self,
        task_id: str,
        stage: StageType,
        feedback: Optional[str],
        count: int,
        regenerate: bool,
    ) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            task = self.store.get(task_id)
            if not task:
                return
            candidates = self._generate_candidates(task, stage, feedback=feedback, count=count)
            task, _ = self._apply_candidates(task, stage, candidates, regenerate=regenerate)
            self._run_validators(task, stage, candidates)
            return

        async def job() -> None:
            task = self.store.get(task_id)
            if not task:
                return
            candidates = await asyncio.to_thread(
                self._generate_candidates, task, stage, feedback, count
            )
            latest = self.store.get(task_id) or task
            latest, _ = self._apply_candidates(latest, stage, candidates, regenerate=regenerate)
            self._run_validators(latest, stage, candidates)

        loop.create_task(job())

    def _apply_candidates(
        self,
        task: Task,
        stage: StageType,
        candidates: List[Candidate],
        regenerate: bool,
    ) -> Tuple[Task, StageArtifact]:
        event_type = "candidates_regenerated" if regenerate else "candidates_generated"
        revision_id = uuid4().hex
        generation_context = candidates[0].generation_context if candidates else {}
        event = Event(
            type=event_type,
            task_id=task.task_id,
            stage=stage,
            payload={
                "revision_id": revision_id,
                "candidates": [c.model_dump() for c in candidates],
                "generation_context": generation_context,
            },
        )
        task = self._emit_event(
            task,
            event,
            sse_event="candidates",
            sse_payload={
                "stage": stage.value,
                "revision_id": revision_id,
                "candidates": [c.model_dump() for c in candidates],
                "generation_context": generation_context,
            },
        )
        return task, task.artifacts[stage]

    def _run_validators(self, task: Task, stage: StageType, candidates: List[Candidate]) -> None:
        validation = validate_non_empty(candidates)
        if validation.warnings and stage in task.artifacts:
            artifact = task.artifacts[stage]
            artifact.warnings.extend(validation.warnings)
        if stage == StageType.activity and candidates and task.entry_point == EntryPoint.tool_seed:
            tool_seed = task.tool_seed
            if tool_seed is None:
                try:
                    tool_seed = ToolSeed(**task.entry_data)
                except Exception:
                    tool_seed = None
            question_chain = []
            if StageType.question_chain in task.artifacts:
                selected = task.artifacts[StageType.question_chain].selected_candidate_id
                for cand in task.artifacts[StageType.question_chain].candidates:
                    if cand.id == selected:
                        question_chain = cand.content.get("question_chain", [])
                        break
            if not question_chain and StageType.driving_question in task.artifacts:
                selected = task.artifacts[StageType.driving_question].selected_candidate_id
                for cand in task.artifacts[StageType.driving_question].candidates:
                    if cand.id == selected:
                        question_chain = cand.content.get("question_chain", [])
                        break
            candidate_to_validate: Optional[Candidate] = None
            artifact = task.artifacts.get(stage)
            if artifact and artifact.selected_candidate_id:
                for cand in artifact.candidates:
                    if cand.id == artifact.selected_candidate_id:
                        candidate_to_validate = cand
                        break
            activity_text = (
                candidate_to_validate.content.get("activity", "") if candidate_to_validate else ""
            )
            if tool_seed is not None and candidate_to_validate is not None:
                alignment = validate_activity_alignment(tool_seed, question_chain, activity_text)
                validation.conflicts.extend(alignment.conflicts)
        for conflict in validation.conflicts:
            task = self._emit_event(
                task,
                Event(
                    type="conflict_detected",
                    task_id=task.task_id,
                    stage=stage,
                    payload={"conflict": conflict.model_dump()},
                ),
                sse_event="conflict",
                sse_payload=conflict.model_dump(),
            )
        self.tracer.log_child(
            root_run_id=task.trace_root_id,
            name=f"validator:{stage.value}",
            run_type="tool",
            inputs={"stage": stage.value, "candidates": len(candidates)},
            outputs={"conflicts": len(validation.conflicts), "warnings": len(validation.warnings)},
            metadata={"task_id": task.task_id, "stage": stage.value, "action": "validate"},
        )

    def _emit_decision(self, task: Task, decision: DecisionResult) -> Task:
        self.tracer.log_child(
            root_run_id=task.trace_root_id,
            name=f"decision:{task.current_stage.value}",
            run_type="chain",
            inputs={"stage": task.current_stage.value},
            outputs={"direction": decision.direction, "next_stage": decision.next_stage.value if decision.next_stage else None},
            metadata={"task_id": task.task_id, "stage": task.current_stage.value, "action": "decision"},
        )
        event = Event(
            type="decision_emitted",
            task_id=task.task_id,
            stage=task.current_stage,
            payload={"decision": decision.model_dump()},
        )
        task = self._emit_event(task, event, sse_event="decision", sse_payload=decision.model_dump())
        message_text = build_decision_message(task, decision)
        message = Message(
            role="assistant",
            text=message_text,
            stage=task.current_stage,
            kind="decision",
        )
        task = self._emit_event(
            task,
            Event(
                type="message_emitted",
                task_id=task.task_id,
                stage=task.current_stage,
                payload={"message": message.model_dump()},
            ),
            sse_event="message",
            sse_payload={"role": message.role, "text": message.text, "stage": message.stage.value if message.stage else None},
        )
        return task

    def _emit_event(
        self,
        task: Task,
        event: Event,
        sse_event: str = "task_updated",
        sse_payload: Optional[Dict[str, Any]] = None,
    ) -> Task:
        if event.trace is None:
            if event.type == "task_created":
                event.trace = {"run_id": event.payload.get("trace_root_id")}
            else:
                event.trace = {"run_id": task.trace_root_id}
        task = apply_event(task, event)
        self.store.save(task)
        self.persistence.save_snapshot(task)
        self.persistence.append_event(event)
        self._publish(
            task.task_id,
            sse_event,
            sse_payload or to_jsonable(task),
            stage=event.stage,
            timestamp=event.timestamp,
            trace=event.trace,
        )
        if event.type == "task_completed":
            self.tracer.end_root(task.trace_root_id, status="completed")
        if event.type == "error_raised":
            self.tracer.end_root(task.trace_root_id, status="error")
        return task

    def _publish(
        self,
        task_id: str,
        event: str,
        data: Dict[str, Any],
        stage: Optional[StageType],
        timestamp: datetime,
        trace: Optional[Dict[str, Any]],
    ) -> None:
        try:
            loop = asyncio.get_running_loop()
            payload = {
                "task_id": task_id,
                "stage": stage.value if isinstance(stage, StageType) else (stage or None),
                "timestamp": timestamp.isoformat(),
                "run_id": (trace or {}).get("run_id"),
                "data": data,
            }
            loop.create_task(self.sse_bus.publish(task_id, {"event": event, "data": payload}))
        except RuntimeError:
            pass
