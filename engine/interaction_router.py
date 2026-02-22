from __future__ import annotations

from typing import Iterable, List, Optional

from core.models import Message
from core.types import DialogueState


class InteractionRouter:
    def route(
        self,
        user_input: str,
        history: Optional[Iterable] = None,
        current_state: DialogueState = DialogueState.exploring,
    ) -> DialogueState:
        text = (user_input or "").strip()
        if not text:
            return current_state
        if self.detect_intent_shift(history, text) >= 0.6:
            return DialogueState.exploring
        if any(keyword in text for keyword in ["确认", "选择", "定稿", "进入下一步"]):
            return DialogueState.generating
        return current_state or DialogueState.exploring

    def detect_intent_shift(self, history: Optional[Iterable], new_input: str) -> float:
        if not history:
            return 0.0
        texts: List[str] = []
        items = list(history)
        for item in items[-3:]:
            if isinstance(item, Message):
                texts.append(item.text or "")
            elif isinstance(item, dict):
                texts.append(str(item.get("content") or item.get("text") or ""))
            else:
                texts.append(str(item))
        recent = " ".join(texts)
        overlap = len(set(recent.split()) & set(new_input.split()))
        base = max(1, len(set(recent.split())))
        return max(0.0, min(1.0, 1.0 - overlap / base))


__all__ = ["InteractionRouter"]
