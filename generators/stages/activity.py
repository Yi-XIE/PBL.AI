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


DISTINCTNESS_RULES = "Each option must be clearly different in activity flow, materials, and student actions. Do not paraphrase."


class ActivityGenerator:
    def generate(self, task: Task, count: int = 3, feedback: Optional[str] = None) -> List[Candidate]:
        driving_question = self._get_driving_question(task)
        question_chain = self._get_question_chain(task)
        tool_seed = get_tool_seed(task)
        template = load_prompt_template("activity.txt")
        prompt = build_prompt(template)
        prompt_context = get_prompt_context(tool_seed)
        llm = get_llm()
        avoid_candidates = collect_avoid_candidates(task, StageType.activity)

        raw_options = self._invoke_options(
            prompt,
            llm,
            driving_question=driving_question,
            question_chain=question_chain,
            prompt_context=prompt_context,
            count=count,
            feedback=feedback,
            avoid_candidates=avoid_candidates,
        )
        raw_options = self._ensure_unique(
            raw_options,
            count=count,
            prompt=prompt,
            llm=llm,
            driving_question=driving_question,
            question_chain=question_chain,
            prompt_context=prompt_context,
            feedback=feedback,
            avoid_candidates=avoid_candidates,
        )

        raw_candidates: List[dict] = []
        for index, raw in enumerate(raw_options):
            candidate_id = chr(65 + index)
            activity_text = raw.get("activity") or raw.get("title") or ""
            raw_candidates.append(
                {
                    "id": candidate_id,
                    "title": self._extract_title(activity_text) or f"Activity Plan {candidate_id}",
                    "activity": activity_text,
                    "rationale": "",
                    "derived_from": ["question_chain"] + (["tool_seed"] if task.entry_point.value == "tool_seed" else []),
                    "alignment_score": 0.0,
                    "generation_context": {
                        "based_on": ["question_chain"],
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

    def _get_question_chain(self, task: Task) -> list:
        selected = get_selected_candidate(task, StageType.question_chain)
        if selected:
            return selected.content.get("question_chain", [])
        selected_dq = get_selected_candidate(task, StageType.driving_question)
        if selected_dq:
            return selected_dq.content.get("question_chain", [])
        return []

    def _template_raw(self, driving_question: str, index: int) -> dict:
        candidate_id = chr(65 + index)
        return {
            "id": candidate_id,
            "title": f"Activity {candidate_id}",
            "activity": f"Template activity {candidate_id} aligned with driving question.",
            "rationale": "",
            "derived_from": ["question_chain"],
            "alignment_score": 0.0,
            "generation_context": {
                "based_on": ["question_chain"],
                "constraints_applied": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    def _duration_guidelines(self, duration: int) -> str:
        if duration == 80:
            return (
                "- Total: 80 minutes (two sessions, 40+40)\n"
                "- Session 1: Activity 1 + Activity 2 (with outputs)\n"
                "- Session 2: Activity 3 + Experiment + Showcase\n"
                "- Must map three activities to three sub-questions"
            )
        if duration <= 45:
            return (
                "- Total: 45 minutes\n"
                "- Suggested: Intro(5) + Explore(15) + Practice(15) + Wrap-up(10)\n"
                "- Include at least one hands-on segment"
            )
        if duration <= 90:
            return (
                "- Total: 90 minutes\n"
                "- Suggested: Intro(10) + Explore(20) + Practice(30) + Showcase(20) + Wrap-up(10)\n"
                "- Include at least one full experiment and one showcase"
            )
        return (
            f"- Total: {duration} minutes\n"
            "- Suggested: Intro(10) + Explore(25) + Practice(40) + Showcase(30) + Wrap-up(15)\n"
            "- Include a full explore-practice-showcase flow"
        )

    def _extract_title(self, text: str) -> str:
        if not text:
            return ""
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned:
                return cleaned.strip("[]")
        return ""

    def _to_candidate(self, raw: dict) -> Candidate:
        payload = to_candidate_payload(raw, "activity")
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
        question_chain: list,
        prompt_context: dict,
        count: int,
        feedback: Optional[str],
        avoid_candidates: List[str],
        force_rewrite: bool = False,
    ) -> List[dict]:
        feedback_text = feedback or "none"
        if force_rewrite:
            feedback_text = f"{feedback_text}; rewrite with a clearly different angle."
        try:
            chain = prompt | llm
            question_chain_str = "\n".join(
                f"{i+1}. {q}" for i, q in enumerate((question_chain or [])[:3])
            )
            duration_guidelines = self._duration_guidelines(prompt_context["duration"])
            safety_constraints = prompt_context["knowledge_snippets"].get("safety_constraints", [])
            if isinstance(safety_constraints, list):
                safety_str = "\n".join(f"- {item}" for item in safety_constraints)
            else:
                safety_str = str(safety_constraints)
            result = chain.invoke(
                {
                    "driving_question": driving_question,
                    "question_chain": question_chain_str or "none",
                    "grade_level": prompt_context["grade_level"],
                    "duration": prompt_context["duration"],
                    "duration_guidelines": duration_guidelines,
                    "context_summary": prompt_context["context_summary"],
                    "knowledge_snippets": prompt_context["knowledge_snippets"].get("grade_rules", ""),
                    "safety_constraints": safety_str,
                    "tool_constraints": prompt_context["tool_constraints"],
                    "user_feedback": feedback_text,
                    "option_count": count,
                    "avoid_candidates": self._format_avoid(avoid_candidates),
                    "distinctness_rules": DISTINCTNESS_RULES,
                }
            )
            payload = extract_json(result.content or "")
            return normalize_options(payload)
        except Exception as exc:
            raise LLMInvocationError("LLM invocation failed for activity") from exc

    def _option_text(self, raw: dict) -> str:
        return raw.get("activity") or raw.get("title") or ""

    def _ensure_unique(
        self,
        raw_options: List[dict],
        *,
        count: int,
        prompt,
        llm,
        driving_question: str,
        question_chain: list,
        prompt_context: dict,
        feedback: Optional[str],
        avoid_candidates: List[str],
    ) -> List[dict]:
        unique: List[dict] = []
        seen_texts: List[str] = list(avoid_candidates)

        for raw in raw_options:
            if len(unique) >= count:
                break
            text = self._option_text(raw)
            if is_duplicate(text, seen_texts):
                replacement = None
                for _ in range(2):
                    regenerated = self._invoke_options(
                        prompt,
                        llm,
                        driving_question=driving_question,
                        question_chain=question_chain,
                        prompt_context=prompt_context,
                        count=1,
                        feedback=feedback,
                        avoid_candidates=seen_texts,
                        force_rewrite=True,
                    )
                    if regenerated:
                        candidate = regenerated[0]
                        candidate_text = self._option_text(candidate)
                        if not is_duplicate(candidate_text, seen_texts):
                            replacement = candidate
                            text = candidate_text
                            break
                        seen_texts.append(candidate_text)
                if replacement is None:
                    raise LLMInvocationError("Duplicate candidates detected for activity")
                raw = replacement
            unique.append(raw)
            seen_texts.append(text)

        while len(unique) < count:
            regenerated = self._invoke_options(
                prompt,
                llm,
                driving_question=driving_question,
                question_chain=question_chain,
                prompt_context=prompt_context,
                count=1,
                feedback=feedback,
                avoid_candidates=seen_texts,
                force_rewrite=True,
            )
            if not regenerated:
                raise LLMInvocationError("Insufficient candidates for activity")
            candidate = regenerated[0]
            candidate_text = self._option_text(candidate)
            if is_duplicate(candidate_text, seen_texts):
                raise LLMInvocationError("Duplicate candidates detected for activity")
            unique.append(candidate)
            seen_texts.append(candidate_text)

        return unique
