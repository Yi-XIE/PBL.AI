from __future__ import annotations

import os
from typing import Iterable, List, Optional


DEFAULT_BLOCKLIST = [
    "魔法",
    "魔幻",
    "咒语",
    "巫师",
    "穿越",
    "外星",
    "异世界",
    "超能力",
    "科幻",
    "未来世界",
    "时空旅行",
    "量子穿梭",
    "magic",
    "wizard",
    "spell",
    "time travel",
    "alien",
    "sci-fi",
    "science fiction",
    "superpower",
]


def _load_blocklist() -> List[str]:
    value = os.getenv("SCENARIO_REALISM_BLOCKLIST", "")
    if not value.strip():
        return DEFAULT_BLOCKLIST
    return [item.strip() for item in value.split(",") if item.strip()]


def find_unrealistic_term(text: str, blocklist: Optional[Iterable[str]] = None) -> Optional[str]:
    if not text:
        return None
    lowered = text.lower()
    terms = blocklist or _load_blocklist()
    for term in terms:
        if term.lower() in lowered:
            return term
    return None


def is_realistic(text: str, blocklist: Optional[Iterable[str]] = None) -> bool:
    return find_unrealistic_term(text, blocklist) is None


__all__ = ["is_realistic", "find_unrealistic_term"]
