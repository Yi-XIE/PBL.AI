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
from utils.question_chain import parse_question_chain


DISTINCTNESS_RULES = "Each option must be substantially different in framing, verb, and context. Do not paraphrase."


class DrivingQuestionGenerator:
    def generate(self, task: Task, count: int = 3, feedback: Optional[str] = None) -> List[Candidate]:
        scenario_text = self._get_scenario(task)
        tool_seed = get_tool_seed(task)
        template = load_prompt_template("driving_question.txt")
        prompt = build_prompt(template)
        prompt_context = get_prompt_context(tool_seed)
        llm = get_llm()
        avoid_candidates = collect_avoid_candidates(task, StageType.driving_question)

        raw_options = self._invoke_options(
            prompt,
            llm,
            scenario_text=scenario_text,
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
            scenario_text=scenario_text,
            prompt_context=prompt_context,
            feedback=feedback,
            avoid_candidates=avoid_candidates,
        )

        raw_candidates: List[dict] = []
        for index, raw in enumerate(raw_options):
            candidate_id = chr(65 + index)
            driving_question = raw.get("driving_question") or raw.get("title") or ""
            question_chain = raw.get("question_chain")
            if isinstance(question_chain, str):
                question_chain = parse_question_chain(question_chain)
            if not isinstance(question_chain, list):
                question_chain = []
            if len(question_chain) >= 3:
                question_chain = question_chain[:3]
            while len(question_chain) < 3:
                question_chain.append("TBD: add an investigable sub-question.")
            raw_candidates.append(
                {
                    "id": candidate_id,
                    "title": driving_question or f"Driving Question {candidate_id}",
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

    def _format_avoid(self, avoid_candidates: List[str]) -> str:
        if not avoid_candidates:
            return "none"
        return "\n".join(f"- {summarize(item)}" for item in avoid_candidates if item)

    def _invoke_options(
        self,
        prompt,
        llm,
        *,
        scenario_text: str,
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
            result = chain.invoke(
                {
                    "scenario": scenario_text,
                    "grade_level": prompt_context["grade_level"],
                    "context_summary": prompt_context["context_summary"],
                    "user_feedback": feedback_text,
                    "option_count": count,
                    "avoid_candidates": self._format_avoid(avoid_candidates),
                    "distinctness_rules": DISTINCTNESS_RULES,
                }
            )
            payload = extract_json(result.content or "")
            return normalize_options(payload)
        except Exception as exc:
            raise LLMInvocationError("LLM invocation failed for driving_question") from exc

    def _option_text(self, raw: dict) -> str:
        dq = raw.get("driving_question") or raw.get("title") or ""
        chain = raw.get("question_chain")
        if isinstance(chain, list):
            chain_text = " ".join(str(item) for item in chain if item)
        else:
            chain_text = str(chain or "")
        return f"{dq} {chain_text}".strip()

    def _ensure_unique(
        self,
        raw_options: List[dict],
        *,
        count: int,
        prompt,
        llm,
        scenario_text: str,
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
                        scenario_text=scenario_text,
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
                    raise LLMInvocationError("Duplicate candidates detected for driving_question")
                raw = replacement
            unique.append(raw)
            seen_texts.append(text)

        while len(unique) < count:
            regenerated = self._invoke_options(
                prompt,
                llm,
                scenario_text=scenario_text,
                prompt_context=prompt_context,
                count=1,
                feedback=feedback,
                avoid_candidates=seen_texts,
                force_rewrite=True,
            )
            if not regenerated:
                raise LLMInvocationError("Insufficient candidates for driving_question")
            candidate = regenerated[0]
            candidate_text = self._option_text(candidate)
            if is_duplicate(candidate_text, seen_texts):
                raise LLMInvocationError("Duplicate candidates detected for driving_question")
            unique.append(candidate)
            seen_texts.append(candidate_text)

        return unique
