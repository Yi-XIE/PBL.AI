from __future__ import annotations

from typing import List, Optional

from datetime import datetime, timezone

from adapters.llm import LLMInvocationError, get_llm
from core.models import Candidate, Task
from core.types import CandidateStatus, StageType
from generators.diversity import collect_avoid_candidates, is_duplicate, summarize
from generators.utils import (
    build_prompt,
    constraints_to_applied_list,
    get_selected_candidate,
    get_prompt_context,
    get_tool_seed,
    extract_json,
    load_prompt_template,
    normalize_derived_from,
    normalize_options,
    to_candidate_payload,
)


DISTINCTNESS_RULES = "Each option must be clearly different in experiment design and materials. Do not paraphrase."


class ExperimentGenerator:
    def generate(self, task: Task, count: int = 3, feedback: Optional[str] = None) -> List[Candidate]:
        tool_seed = get_tool_seed(task)
        driving_question = self._get_driving_question(task)
        activity_summary = self._get_activity_summary(task)
        template = load_prompt_template("experiment.txt")
        prompt = build_prompt(template)
        prompt_context = get_prompt_context(tool_seed, task)
        llm = get_llm()
        avoid_candidates = collect_avoid_candidates(task, StageType.experiment)

        raw_options = self._invoke_options(
            prompt,
            llm,
            driving_question=driving_question,
            activity_summary=activity_summary,
            prompt_context=prompt_context,
            count=count,
            feedback=feedback,
            avoid_candidates=avoid_candidates,
            derived_from=self._derived_from(task, driving_question),
        )
        raw_options = self._ensure_unique(
            raw_options,
            count=count,
            prompt=prompt,
            llm=llm,
            driving_question=driving_question,
            activity_summary=activity_summary,
            prompt_context=prompt_context,
            feedback=feedback,
            avoid_candidates=avoid_candidates,
            derived_from=self._derived_from(task, driving_question),
        )

        raw_candidates: List[dict] = []
        derived_from = self._derived_from(task, driving_question)
        for index, raw in enumerate(raw_options):
            candidate_id = chr(65 + index)
            text = raw.get("experiment") or raw.get("title") or ""
            raw_candidates.append(
                {
                    "id": candidate_id,
                    "title": self._extract_title(text) or f"Experiment Plan {candidate_id}",
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

    def _derived_from(self, task: Task, driving_question: str) -> List[str]:
        derived_from = ["activity"]
        if driving_question:
            derived_from.append("driving_question")
        if task.entry_point.value == "tool_seed":
            derived_from.append("tool_seed")
        return derived_from

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

    def _format_avoid(self, avoid_candidates: List[str]) -> str:
        if not avoid_candidates:
            return "none"
        return "\n".join(f"- {summarize(item)}" for item in avoid_candidates if item)

    def _invoke_options(
        self,
        prompt,
        llm,
        *,
        driving_question: str,
        activity_summary: str,
        prompt_context: dict,
        count: int,
        feedback: Optional[str],
        avoid_candidates: List[str],
        derived_from: List[str],
        force_rewrite: bool = False,
    ) -> List[dict]:
        feedback_text = feedback or "none"
        if force_rewrite:
            feedback_text = f"{feedback_text}; rewrite with a clearly different angle."
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
                    "user_feedback": feedback_text,
                    "option_count": count,
                    "avoid_candidates": self._format_avoid(avoid_candidates),
                    "distinctness_rules": DISTINCTNESS_RULES,
                    "derived_from": ", ".join(derived_from),
                    "creative_intent": prompt_context["creative_intent"],
                    "decision_summary": prompt_context["decision_summary"],
                    "working_memory_notes": prompt_context["working_memory_notes"],
                }
            )
            payload = extract_json(result.content or "")
            return normalize_options(payload)
        except Exception as exc:
            raise LLMInvocationError("LLM invocation failed for experiment") from exc

    def _option_text(self, raw: dict) -> str:
        return raw.get("experiment") or raw.get("title") or ""

    def _is_valid(self, raw: dict) -> bool:
        text = self._option_text(raw)
        return bool(text and len(str(text).strip()) >= 20)

    def _ensure_unique(
        self,
        raw_options: List[dict],
        *,
        count: int,
        prompt,
        llm,
        driving_question: str,
        activity_summary: str,
        prompt_context: dict,
        feedback: Optional[str],
        avoid_candidates: List[str],
        derived_from: List[str],
    ) -> List[dict]:
        unique: List[dict] = []
        seen_texts: List[str] = list(avoid_candidates)

        for raw in raw_options:
            if len(unique) >= count:
                break
            text = self._option_text(raw)
            if (not self._is_valid(raw)) or is_duplicate(text, seen_texts):
                replacement = None
                for _ in range(2):
                    regenerated = self._invoke_options(
                        prompt,
                        llm,
                        driving_question=driving_question,
                        activity_summary=activity_summary,
                        prompt_context=prompt_context,
                        count=1,
                        feedback=feedback,
                        avoid_candidates=seen_texts,
                        derived_from=derived_from,
                        force_rewrite=True,
                    )
                    if regenerated:
                        candidate = regenerated[0]
                        candidate_text = self._option_text(candidate)
                        if self._is_valid(candidate) and not is_duplicate(candidate_text, seen_texts):
                            replacement = candidate
                            text = candidate_text
                            break
                        seen_texts.append(candidate_text)
                if replacement is None:
                    raise LLMInvocationError("Duplicate candidates detected for experiment")
                raw = replacement
            unique.append(raw)
            seen_texts.append(text)

        while len(unique) < count:
            regenerated = self._invoke_options(
                prompt,
                llm,
                driving_question=driving_question,
                activity_summary=activity_summary,
                prompt_context=prompt_context,
                count=1,
                feedback=feedback,
                avoid_candidates=seen_texts,
                derived_from=derived_from,
                force_rewrite=True,
            )
            if not regenerated:
                raise LLMInvocationError("Insufficient candidates for experiment")
            candidate = regenerated[0]
            candidate_text = self._option_text(candidate)
            if (not self._is_valid(candidate)) or is_duplicate(candidate_text, seen_texts):
                raise LLMInvocationError("Duplicate candidates detected for experiment")
            unique.append(candidate)
            seen_texts.append(candidate_text)

        return unique
