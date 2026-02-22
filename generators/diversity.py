from __future__ import annotations

import json
import re
from typing import Any, Iterable, List

from core.models import Task
from core.types import StageType


def normalize_text(text: str) -> str:
    if not text:
        return ""
    lowered = text.lower()
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "", lowered)
    return cleaned


def _ngrams(text: str, n: int = 3) -> set[str]:
    if not text:
        return set()
    if len(text) <= n:
        return {text}
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def similarity(a: str, b: str, n: int = 3) -> float:
    norm_a = normalize_text(a)
    norm_b = normalize_text(b)
    if not norm_a or not norm_b:
        return 0.0
    grams_a = _ngrams(norm_a, n=n)
    grams_b = _ngrams(norm_b, n=n)
    if not grams_a or not grams_b:
        return 0.0
    intersection = grams_a.intersection(grams_b)
    union = grams_a.union(grams_b)
    return len(intersection) / max(len(union), 1)


def is_duplicate(text: str, existing_texts: Iterable[str], threshold: float = 0.85) -> bool:
    if not normalize_text(text):
        return True
    for existing in existing_texts:
        if similarity(text, existing) >= threshold:
            return True
    return False


def summarize(text: str, limit: int = 160) -> str:
    if not text:
        return ""
    trimmed = text.strip().replace("\n", " ")
    return trimmed[:limit]


def _value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(item) for item in value if item is not None)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def extract_text_from_content(content: Any, stage_key: str) -> str:
    if content is None:
        return ""
    if isinstance(content, dict):
        if stage_key in content:
            return _value_to_text(content.get(stage_key))
        if stage_key == "driving_question":
            return _value_to_text(content.get("driving_question"))
        if stage_key == "question_chain":
            return _value_to_text(content.get("question_chain"))
        if stage_key == "scenario":
            return _value_to_text(content.get("scenario"))
        if stage_key == "activity":
            return _value_to_text(content.get("activity"))
        if stage_key == "experiment":
            return _value_to_text(content.get("experiment"))
        return json.dumps(content, ensure_ascii=False)
    return _value_to_text(content)


def extract_text_from_raw(raw: Any, stage_key: str) -> str:
    if raw is None:
        return ""
    if isinstance(raw, dict):
        if "content" in raw:
            return extract_text_from_content(raw.get("content"), stage_key)
        if stage_key in raw:
            return _value_to_text(raw.get(stage_key))
        for key in ["driving_question", "question_chain", "scenario", "activity", "experiment", "title"]:
            if key in raw:
                return _value_to_text(raw.get(key))
        return json.dumps(raw, ensure_ascii=False)
    return _value_to_text(raw)


def collect_avoid_candidates(task: Task, stage: StageType, max_items: int = 6) -> List[str]:
    artifact = task.artifacts.get(stage)
    if not artifact:
        return []
    items: List[str] = []
    for cand in artifact.candidates:
        text = summarize(extract_text_from_content(cand.content, stage.value))
        if text:
            items.append(text)
    for history in reversed(artifact.history):
        for cand in history.get("candidates", []):
            text = summarize(extract_text_from_raw(cand, stage.value))
            if text:
                items.append(text)
        if len(items) >= max_items:
            break
    deduped: List[str] = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
        if len(deduped) >= max_items:
            break
    return deduped


__all__ = [
    "collect_avoid_candidates",
    "extract_text_from_content",
    "extract_text_from_raw",
    "is_duplicate",
    "similarity",
    "summarize",
]
