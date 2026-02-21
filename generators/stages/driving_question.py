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


class DrivingQuestionGenerator:
    def generate(self, task: Task, count: int = 3, feedback: Optional[str] = None) -> List[Candidate]:
        scenario_text = self._get_scenario(task)
        tool_seed = get_tool_seed(task)
        template = load_prompt_template("driving_question.txt")
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
                        "scenario": scenario_text,
                        "grade_level": prompt_context["grade_level"],
                        "context_summary": prompt_context["context_summary"],
                        "user_feedback": feedback_text or "none",
                    }
                )
                response_text = result.content or ""
                driving_question = self._extract_driving_question(response_text)
                question_chain = parse_question_chain(response_text)
                if len(question_chain) >= 3:
                    question_chain = question_chain[:3]
                while len(question_chain) < 3:
                    question_chain.append("TBD: add an investigable sub-question.")
                raw_candidates.append(
                    {
                        "id": chr(65 + index),
                        "title": driving_question or f"Driving Question {chr(65 + index)}",
                        "driving_question": driving_question,
                        "question_chain": question_chain,
                        "rationale": "",
                        "derived_from": ["scenario"],
                        "alignment_score": 0.0,
                        "generation_context": {
                            "based_on": ["scenario"],
                            "constraints_applied": constraints_to_applied_list(tool_seed.constraints),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                )
            except Exception as exc:
                raise LLMInvocationError("LLM invocation failed for driving_question") from exc

        return [self._to_candidate(raw) for raw in raw_candidates]

    def _get_scenario(self, task: Task) -> str:
        selected = get_selected_candidate(task, StageType.scenario)
        if selected and "scenario" in selected.content:
            return selected.content.get("scenario", "")
        if "scenario" in task.entry_data:
            value = task.entry_data.get("scenario")
            if isinstance(value, dict):
                return value.get("scenario", "")
            if isinstance(value, str):
                return value
        return ""

    def _template_raw(self, scenario: str, index: int) -> dict:
        candidate_id = chr(65 + index)
        return {
            "id": candidate_id,
            "title": f"Template driving question {candidate_id}",
            "driving_question": f"Template driving question {candidate_id} based on scenario.",
            "question_chain": [
                f"Template sub-question {candidate_id}-1",
                f"Template sub-question {candidate_id}-2",
                f"Template sub-question {candidate_id}-3",
            ],
            "rationale": "",
            "derived_from": ["scenario"],
            "alignment_score": 0.0,
            "generation_context": {
                "based_on": ["scenario"],
                "constraints_applied": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    def _extract_driving_question(self, text: str) -> str:
        if not text:
            return ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for i, line in enumerate(lines):
            if line.startswith("###") and "driving" in line.lower():
                if i + 1 < len(lines):
                    return lines[i + 1].strip("[]")
        for line in lines:
            if not line.startswith("#"):
                return line.strip("[]")
        return lines[0].strip("[]") if lines else ""

    def _to_candidate(self, raw: dict) -> Candidate:
        payload = to_candidate_payload(raw, "driving_question")
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
