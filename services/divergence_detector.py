from __future__ import annotations

from core.models import CreativeContext


class DivergenceDetector:
    def detect(self, context: CreativeContext, user_input: str) -> float:
        if not context.original_intent:
            return 0.0
        base = set(context.original_intent.split())
        now = set((user_input or "").split())
        if not base:
            return 0.0
        overlap = len(base & now)
        return max(0.0, min(1.0, 1.0 - overlap / max(1, len(base))))


__all__ = ["DivergenceDetector"]
