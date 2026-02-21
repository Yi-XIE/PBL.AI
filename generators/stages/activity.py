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


class ActivityGenerator:
    def generate(self, task: Task, count: int = 3, feedback: Optional[str] = None) -> List[Candidate]:
        driving_question = self._get_driving_question(task)
        question_chain = self._get_question_chain(task)
        tool_seed = get_tool_seed(task)
        template = load_prompt_template("activity.txt")
        prompt = build_prompt(template)
        prompt_context = get_prompt_context(tool_seed)
        llm = get_llm()

        raw_candidates: List[dict] = []
        for index in range(count):
            hint = f"Provide option {index + 1} with a distinct angle."
            feedback_text = f"{feedback}; {hint}" if feedback else hint
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
                        "user_feedback": feedback_text or "none",
                    }
                )
                activity_text = result.content or ""
                raw_candidates.append(
                    {
                        "id": chr(65 + index),
                        "title": self._extract_title(activity_text) or f"Activity Plan {chr(65 + index)}",
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
            except Exception as exc:
                raise LLMInvocationError("LLM invocation failed for activity") from exc

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
