from __future__ import annotations

from typing import Any, Dict, List, Optional

from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

from core.models import Candidate, StageArtifact, Task, ToolSeed
from core.types import StageType


def get_tool_seed(task: Task) -> ToolSeed:
    if task.tool_seed:
        return task.tool_seed
    try:
        return ToolSeed(**task.entry_data)
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


def get_prompt_context(tool_seed: ToolSeed) -> Dict[str, Any]:
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
    }
