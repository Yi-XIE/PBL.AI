from __future__ import annotations

from typing import List, Optional

from datetime import datetime, timezone

from adapters.llm import get_llm
from core.models import Candidate, Task
from core.types import CandidateStatus
from generators.utils import (
    build_prompt,
    constraints_to_applied_list,
    get_prompt_context,
    get_tool_seed,
    load_prompt_template,
    normalize_derived_from,
    to_candidate_payload,
)


class ScenarioGenerator:
    def generate(self, task: Task, count: int = 3, feedback: Optional[str] = None) -> List[Candidate]:
        tool_seed = get_tool_seed(task)
        template = load_prompt_template("scenario.txt")
        prompt = build_prompt(template)
        prompt_context = get_prompt_context(tool_seed)
        try:
            llm = get_llm()
        except Exception:
            llm = None

        raw_candidates: List[dict] = []
        for index in range(count):
            hint = f"Provide option {index + 1} with a distinct angle."
            feedback_text = f"{feedback}; {hint}" if feedback else hint
            if llm is None:
                raw_candidates.append(self._template_raw(tool_seed, index))
                continue
            try:
                chain = prompt | llm
                result = chain.invoke(
                    {
                        "topic": prompt_context["topic"],
                        "grade_level": prompt_context["grade_level"],
                        "duration": prompt_context["duration"],
                        "context_summary": prompt_context["context_summary"],
                        "grade_rules": prompt_context["knowledge_snippets"].get("grade_rules", ""),
                        "topic_template": prompt_context["knowledge_snippets"].get("topic_template", ""),
                        "user_feedback": feedback_text or "none",
                    }
                )
                scenario_text = result.content or ""
                raw_candidates.append(
                    {
                        "id": chr(65 + index),
                        "title": self._extract_title(scenario_text) or f"Scenario {chr(65 + index)}",
                        "scenario": scenario_text,
                        "rationale": "",
                        "derived_from": ["tool_seed"],
                        "alignment_score": 0.0,
                        "generation_context": {
                            "based_on": ["tool_seed"],
                            "constraints_applied": constraints_to_applied_list(tool_seed.constraints),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                )
            except Exception:
                raw_candidates.append(self._template_raw(tool_seed, index))

        return [self._to_candidate(raw) for raw in raw_candidates]

    def _template_raw(self, tool_seed, index: int) -> dict:
        candidate_id = chr(65 + index)
        return {
            "id": candidate_id,
            "title": f"Template Scenario {candidate_id}",
            "scenario": f"Template scenario for {tool_seed.user_intent or tool_seed.tool_name or 'your topic'} (Option {candidate_id}).",
            "rationale": "",
            "derived_from": ["tool_seed"],
            "alignment_score": 0.0,
            "generation_context": {
                "based_on": ["tool_seed"],
                "constraints_applied": constraints_to_applied_list(tool_seed.constraints),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    def _extract_title(self, text: str) -> str:
        if not text:
            return ""
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("#"):
                return cleaned.strip("[]")
        return ""

    def _to_candidate(self, raw: dict) -> Candidate:
        payload = to_candidate_payload(raw, "scenario")
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
