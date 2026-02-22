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
    get_prompt_context,
    get_tool_seed,
    extract_json,
    load_prompt_template,
    normalize_derived_from,
    normalize_options,
    to_candidate_payload,
)
from validators.scenario_realism import is_realistic


DISTINCTNESS_RULES = "Each option must be substantially different in setting and learner role. Do not paraphrase."


class ScenarioGenerator:
    def generate(self, task: Task, count: int = 3, feedback: Optional[str] = None) -> List[Candidate]:
        tool_seed = get_tool_seed(task)
        template = load_prompt_template("scenario.txt")
        prompt = build_prompt(template)
        prompt_context = get_prompt_context(tool_seed, task)
        llm = get_llm()

        raw_candidates: List[dict] = []
        provided_scenario = None
        if task.entry_point.value == "scenario":
            provided_scenario = task.entry_data.get("scenario")
            if isinstance(provided_scenario, dict):
                provided_scenario = provided_scenario.get("scenario", "")
            if isinstance(provided_scenario, str):
                provided_scenario = provided_scenario.strip()
            if not provided_scenario:
                provided_scenario = None

        start_index = 0
        if provided_scenario:
            raw_candidates.append(
                {
                    "id": "A",
                    "title": self._extract_title(provided_scenario) or "Provided Scenario",
                    "scenario": provided_scenario,
                    "rationale": "",
                    "derived_from": ["entry_point"],
                    "alignment_score": 0.0,
                    "generation_context": {
                        "based_on": ["entry_point"],
                        "constraints_applied": constraints_to_applied_list(tool_seed.constraints),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }
            )
            start_index = 1
        avoid_candidates = collect_avoid_candidates(task, StageType.scenario)
        if provided_scenario:
            avoid_candidates.insert(0, summarize(provided_scenario))

        count_needed = count - start_index
        if count_needed > 0:
            raw_options = self._invoke_options(
                prompt,
                llm,
                prompt_context=prompt_context,
                count=count_needed,
                feedback=feedback,
                avoid_candidates=avoid_candidates,
            )
            raw_options = self._ensure_unique(
                raw_options,
                count=count_needed,
                prompt=prompt,
                llm=llm,
                prompt_context=prompt_context,
                feedback=feedback,
                avoid_candidates=avoid_candidates,
            )

            for index, raw in enumerate(raw_options):
                option_index = start_index + index
                candidate_id = chr(65 + option_index)
                scenario_text = raw.get("scenario") or raw.get("title") or ""
                raw_candidates.append(
                    {
                        "id": candidate_id,
                        "title": self._extract_title(scenario_text) or f"Scenario {candidate_id}",
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

    def _format_avoid(self, avoid_candidates: List[str]) -> str:
        if not avoid_candidates:
            return "none"
        return "\n".join(f"- {summarize(item)}" for item in avoid_candidates if item)

    def _invoke_options(
        self,
        prompt,
        llm,
        *,
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
                    "topic": prompt_context["topic"],
                    "grade_level": prompt_context["grade_level"],
                    "duration": prompt_context["duration"],
                    "context_summary": prompt_context["context_summary"],
                    "grade_rules": prompt_context["knowledge_snippets"].get("grade_rules", ""),
                    "topic_template": prompt_context["knowledge_snippets"].get("topic_template", ""),
                    "user_feedback": feedback_text,
                    "option_count": count,
                    "avoid_candidates": self._format_avoid(avoid_candidates),
                    "distinctness_rules": DISTINCTNESS_RULES,
                    "creative_intent": prompt_context["creative_intent"],
                    "decision_summary": prompt_context["decision_summary"],
                    "working_memory_notes": prompt_context["working_memory_notes"],
                }
            )
            payload = extract_json(result.content or "")
            return normalize_options(payload)
        except Exception as exc:
            raise LLMInvocationError("LLM invocation failed for scenario") from exc

    def _option_text(self, raw: dict) -> str:
        return raw.get("scenario") or raw.get("title") or ""

    def _is_valid(self, raw: dict) -> bool:
        text = self._option_text(raw)
        return bool(text and text.strip())

    def _ensure_unique(
        self,
        raw_options: List[dict],
        *,
        count: int,
        prompt,
        llm,
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
            if (not self._is_valid(raw)) or is_duplicate(text, seen_texts) or not is_realistic(text):
                replacement = None
                for _ in range(2):
                    regenerated = self._invoke_options(
                        prompt,
                        llm,
                        prompt_context=prompt_context,
                        count=1,
                        feedback=feedback,
                        avoid_candidates=seen_texts,
                        force_rewrite=True,
                    )
                    if regenerated:
                        candidate = regenerated[0]
                        candidate_text = self._option_text(candidate)
                        if (
                            self._is_valid(candidate)
                            and not is_duplicate(candidate_text, seen_texts)
                            and is_realistic(candidate_text)
                        ):
                            replacement = candidate
                            text = candidate_text
                            break
                        seen_texts.append(candidate_text)
                if replacement is None:
                    raise LLMInvocationError("Duplicate or unrealistic candidates detected for scenario")
                raw = replacement
            unique.append(raw)
            seen_texts.append(text)

        while len(unique) < count:
            regenerated = self._invoke_options(
                prompt,
                llm,
                prompt_context=prompt_context,
                count=1,
                feedback=feedback,
                avoid_candidates=seen_texts,
                force_rewrite=True,
            )
            if not regenerated:
                raise LLMInvocationError("Insufficient candidates for scenario")
            candidate = regenerated[0]
            candidate_text = self._option_text(candidate)
            if (
                not self._is_valid(candidate)
                or is_duplicate(candidate_text, seen_texts)
                or not is_realistic(candidate_text)
            ):
                raise LLMInvocationError("Duplicate or unrealistic candidates detected for scenario")
            unique.append(candidate)
            seen_texts.append(candidate_text)

        return unique
