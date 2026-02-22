from __future__ import annotations

from typing import Optional


class IntentClarifier:
    def build_clarification(self, user_input: str) -> Optional[str]:
        text = (user_input or "").strip()
        if not text:
            return "请补充你想解决的真实问题或学习目标。"
        if len(text) < 6:
            return "可以再具体一点吗？例如希望学生解决什么真实问题。"
        return None


__all__ = ["IntentClarifier"]
