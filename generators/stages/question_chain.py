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
from utils.question_chain import parse_question_chain


class QuestionChainGenerator:
    def generate(self, task: Task, count: int = 3, feedback: Optional[str] = None) -> List[Candidate]:
        driving_question = self._get_driving_question(task)
        tool_seed = get_tool_seed(task)
        template = load_prompt_template("question_chain.txt")
        prompt = build_prompt(template)
        prompt_context = get_prompt_context(tool_seed)
        llm = get_llm()

        raw_candidates: List[dict] = []
        for index in range(count):
            hint = f"Provide option {index + 1} with a distinct angle."
            feedback_text = f"{feedback}; {hint}" if feedback else hint
            try:
                chain = prompt | llm
                result = chain.invoke(
                    {
                        "driving_question": driving_question,
                        "grade_level": prompt_context["grade_level"],
                        "context_summary": prompt_context["context_summary"],
                        "user_feedback": feedback_text or "none",
                    }
                )
                questions = parse_question_chain(result.content or "")
                if len(questions) >= 3:
                    questions = questions[:3]
                while len(questions) < 3:
                    questions.append("TBD: add a sub-question.")
                raw_candidates.append(
                    {
                        "id": chr(65 + index),
                        "title": questions[0] if questions else f"Question Chain {chr(65 + index)}",
                        "question_chain": questions,
                        "rationale": "",
                        "derived_from": ["driving_question"],
                        "alignment_score": 0.0,
                        "generation_context": {
                            "based_on": ["driving_question"],
                            "constraints_applied": constraints_to_applied_list(tool_seed.constraints),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                )
            except Exception as exc:
                raise LLMInvocationError("LLM invocation failed for question_chain") from exc

        return [self._to_candidate(raw) for raw in raw_candidates]

    def _get_driving_question(self, task: Task) -> str:
        selected = get_selected_candidate(task, StageType.driving_question)
        if selected and "driving_question" in selected.content:
            return selected.content.get("driving_question", "")
        return ""

    def _template_raw(self, driving_question: str, index: int) -> dict:
        candidate_id = chr(65 + index)
        return {
            "id": candidate_id,
            "title": f"Template chain {candidate_id}",
            "question_chain": [
                f"Template chain {candidate_id}-1",
                f"Template chain {candidate_id}-2",
                f"Template chain {candidate_id}-3",
            ],
            "rationale": "",
            "derived_from": ["driving_question"],
            "alignment_score": 0.0,
            "generation_context": {
                "based_on": ["driving_question"],
                "constraints_applied": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    def _to_candidate(self, raw: dict) -> Candidate:
        payload = to_candidate_payload(raw, "question_chain")
        if "question_chain" in raw:
            payload["question_chain"] = raw.get("question_chain", [])
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
