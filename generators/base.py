from __future__ import annotations

from typing import List, Optional, Protocol

from core.models import Candidate, Task


class StageGenerator(Protocol):
    def generate(self, task: Task, count: int = 3, feedback: Optional[str] = None) -> List[Candidate]:
        ...
