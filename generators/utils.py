from __future__ import annotations

from typing import Any, Dict, List, Optional

from pathlib import Path
import json
import re

from langchain_core.prompts import ChatPromptTemplate

from core.models import Candidate, StageArtifact, Task, ToolSeed
from core.types import StageType
from utils.intake import intake_to_constraints


def get_tool_seed(task: Task) -> ToolSeed:
    if task.tool_seed:
        return task.tool_seed
    entry_data = task.entry_data or {}
    if isinstance(entry_data, dict) and isinstance(entry_data.get("tool_seed"), dict):
        entry_data = entry_data.get("tool_seed") or {}
    filtered = {}
    if isinstance(entry_data, dict):
        for key in ("tool_name", "algorithms", "affordances", "constraints", "user_intent"):
            if key in entry_data:
                filtered[key] = entry_data.get(key)
        if "constraints" not in filtered and "intake" in entry_data:
            filtered["constraints"] = intake_to_constraints(entry_data.get("intake") or {})
        if "user_intent" not in filtered:
            inferred = ""
            if isinstance(entry_data.get("scenario"), str):
                inferred = entry_data.get("scenario", "")
            if not inferred and "constraints" in filtered:
                inferred = (filtered.get("constraints") or {}).get("topic", "")
            filtered["user_intent"] = inferred
        if "tool_name" not in filtered:
            filtered["tool_name"] = filtered.get("user_intent") or ""
    try:
        return ToolSeed(**filtered)
    except Exception:
        return ToolSeed(tool_name="", algorithms=[], affordances=[], constraints={}, user_intent="")


def get_selected_candidate(task: Task, stage: StageType) -> Optional[Candidate]:
    artifact: Optional[StageArtifact] = task.artifacts.get(stage)
    if not artifact or not artifact.selected_candidate_id:
        return None
    for cand in artifact.candidates:
        if cand.id == artifact.selected_candidate_id:
            return cand
    return None


def to_candidate_payload(raw: Dict[str, Any], stage_key: str) -> Dict[str, Any]:
    if stage_key in raw:
        return {stage_key: raw[stage_key]}
    return {k: v for k, v in raw.items() if k not in {"id", "title", "rationale", "derived_from", "alignment_score", "generation_context"}}


def normalize_derived_from(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, dict):
        return [str(item) for item in value.keys()]
    return [str(value)]


def constraints_to_applied_list(constraints: Dict[str, Any]) -> List[str]:
    applied: List[str] = []
    for key, value in (constraints or {}).items():
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                applied.append(f"{key}:{item}")
        else:
            applied.append(f"{key}:{value}")
    return applied


def load_prompt_template(name: str) -> str:
    base_dir = Path(__file__).resolve().parents[1] / "prompts"
    path = base_dir / name
    return path.read_text(encoding="utf-8")


def build_prompt(template: str) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(template)


def extract_json(text: str) -> Any:
    if not text:
        raise ValueError("Empty LLM response")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = cleaned.strip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
    raise ValueError("No JSON object found in LLM response")


def normalize_options(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        options = payload.get("options") or payload.get("candidates") or payload.get("items")
        if isinstance(options, list):
            return [item for item in options if isinstance(item, dict)]
    raise ValueError("Invalid options payload")


def _truncate(text: str, limit: int = 160) -> str:
    if not text:
        return ""
    cleaned = str(text).replace("\n", " ").strip()
    return cleaned[:limit]


def _summarize_decision(entry: Any) -> str:
    if not isinstance(entry, dict):
        return _truncate(str(entry))
    if entry.get("type") == "intent_updated":
        before = entry.get("before", "")
        after = entry.get("after", "")
        return _truncate(f"intent: {before} -> {after}")
    direction = entry.get("direction")
    next_stage = entry.get("next_stage")
    if isinstance(next_stage, dict):
        next_stage = next_stage.get("value") or next_stage.get("stage") or ""
    if direction:
        return _truncate(f"decision: {direction} {next_stage}".strip())
    if entry.get("type"):
        return _truncate(f"{entry.get('type')}: {entry}")
    return _truncate(str(entry))


def _summarize_decision_history(history: List[Dict[str, Any]], limit: int = 3) -> str:
    if not history:
        return "none"
    items = [_summarize_decision(item) for item in history[-limit:]]
    return " | ".join([item for item in items if item]) or "none"


def _build_creative_intent(task: Optional[Task]) -> str:
    if not task:
        return "none"
    context = task.creative_context
    parts: List[str] = []
    if context.original_intent:
        parts.append(f"intent:{context.original_intent}")
    if context.anchor_concepts:
        parts.append(f"anchors:{', '.join(context.anchor_concepts[:5])}")
    if context.key_constraints:
        parts.append(f"constraints:{', '.join(context.key_constraints[:5])}")
    return " | ".join(parts) if parts else "none"


def _summarize_working_memory(task: Optional[Task], limit: int = 3) -> str:
    if not task:
        return "none"
    notes = task.working_memory.notes[-limit:]
    return " | ".join([_truncate(note, 120) for note in notes if note]) or "none"


def get_prompt_context(tool_seed: ToolSeed, task: Optional[Task] = None) -> Dict[str, Any]:
    constraints = tool_seed.constraints or {}
    return {
        "topic": constraints.get("topic") or tool_seed.user_intent or tool_seed.tool_name,
        "grade_level": constraints.get("grade", ""),
        "duration": int(constraints.get("duration", 0) or 0),
        "context_summary": constraints.get("context_summary", tool_seed.user_intent or ""),
        "knowledge_snippets": constraints.get("knowledge_snippets", {}),
        "tool_constraints": constraints.get("tool_constraints", ""),
        "classroom_mode": constraints.get("classroom_mode", "normal"),
        "classroom_context": constraints.get("classroom_context", ""),
        "creative_intent": _build_creative_intent(task),
        "decision_summary": _summarize_decision_history(
            task.decision_history if task else []
        ),
        "working_memory_notes": _summarize_working_memory(task),
    }
