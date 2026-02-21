from __future__ import annotations

from typing import List, Optional

from datetime import datetime, timezone

from adapters.llm import LLMInvocationError, get_llm
from core.models import Candidate, Task
from core.types import CandidateStatus, StageType
from generators.utils import (
    build_prompt,
    constraints_to_applied_list,
    get_selected_candidate,
    get_prompt_context,
    get_tool_seed,
    load_prompt_template,
    normalize_derived_from,
    to_candidate_payload,
)


class ExperimentGenerator:
    def generate(self, task: Task, count: int = 3, feedback: Optional[str] = None) -> List[Candidate]:
        tool_seed = get_tool_seed(task)
        driving_question = self._get_driving_question(task)
        activity_summary = self._get_activity_summary(task)
        template = load_prompt_template("experiment.txt")
        prompt = build_prompt(template)
        prompt_context = get_prompt_context(tool_seed)
        llm = get_llm()

        raw_candidates: List[dict] = []
        for index in range(count):
            hint = f"Provide option {index + 1} with a distinct angle."
            feedback_text = f"{feedback}; {hint}" if feedback else hint
            derived_from = ["activity"]
            if driving_question:
                derived_from.append("driving_question")
            if task.entry_point.value == "tool_seed":
                derived_from.append("tool_seed")
            try:
                chain = prompt | llm
                safety_constraints = prompt_context["knowledge_snippets"].get("safety_constraints", [])
                if isinstance(safety_constraints, list):
                    safety_str = "\n".join(f"- {item}" for item in safety_constraints)
                else:
                    safety_str = str(safety_constraints)
                result = chain.invoke(
                    {
                        "topic": prompt_context["topic"],
                        "grade_level": prompt_context["grade_level"],
                        "driving_question": driving_question,
                        "activity_summary": activity_summary,
                        "context_summary": prompt_context["context_summary"],
                        "knowledge_snippets": prompt_context["knowledge_snippets"].get("grade_rules", ""),
                        "safety_constraints": safety_str,
                        "classroom_mode": prompt_context["classroom_mode"],
                        "classroom_context": prompt_context["classroom_context"] or "standard classroom",
                        "user_feedback": feedback_text or "none",
                    }
                )
                text = result.content or ""
                raw_candidates.append(
                    {
                        "id": chr(65 + index),
                        "title": self._extract_title(text) or f"Experiment Plan {chr(65 + index)}",
                        "experiment": text,
                        "rationale": "",
                        "derived_from": derived_from,
                        "alignment_score": 0.0,
                        "generation_context": {
                            "based_on": derived_from,
                            "constraints_applied": constraints_to_applied_list(tool_seed.constraints),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                )
            except Exception as exc:
                raise LLMInvocationError("LLM invocation failed for experiment") from exc

        return [self._to_candidate(raw) for raw in raw_candidates]

    def _get_driving_question(self, task: Task) -> str:
        selected = get_selected_candidate(task, StageType.driving_question)
        if selected and "driving_question" in selected.content:
            return selected.content.get("driving_question", "")
        return ""

    def _get_activity_summary(self, task: Task) -> str:
        selected = get_selected_candidate(task, StageType.activity)
        if selected and "activity" in selected.content:
            return selected.content.get("activity", "")
        return ""

    def _template_raw(
        self,
        topic: str,
        index: int,
        derived_from: List[str],
        constraints: dict,
    ) -> dict:
        candidate_id = chr(65 + index)
        return {
            "id": candidate_id,
            "title": f"Experiment {candidate_id}",
            "experiment": f"Template experiment {candidate_id} for {topic or 'the topic'}.",
            "rationale": "",
            "derived_from": derived_from,
            "alignment_score": 0.0,
            "generation_context": {
                "based_on": derived_from,
                "constraints_applied": constraints_to_applied_list(constraints),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    def _extract_title(self, text: str) -> str:
        if not text:
            return ""
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned:
                return cleaned.strip("[]")
        return ""

    def _to_candidate(self, raw: dict) -> Candidate:
        payload = to_candidate_payload(raw, "experiment")
        return Candidate(
            id=raw.get("id", ""),
            title=raw.get("title", ""),
            status=CandidateStatus.generated,
            content=payload,
            rationale=raw.get("rationale", ""),
            derived_from=normalize_derived_from(raw.get("derived_from")),
            alignment_score=raw.get("alignment_score", 0.0),
            generation_context=raw.get("generation_context", {}),
        )
