from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from core.models import Task
from engine.reducer import Event
from utils.serialization import dumps_json, to_jsonable


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._tasks: Dict[str, Task] = {}

    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def save(self, task: Task) -> None:
        self._tasks[task.task_id] = task

    def list(self) -> List[Task]:
        return list(self._tasks.values())


class JsonPersistence:
    def __init__(self, base_dir: str = "data") -> None:
        self.base_dir = Path(base_dir)
        self.tasks_dir = self.base_dir / "tasks"
        self.events_dir = self.base_dir / "events"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, task: Task) -> None:
        path = self.tasks_dir / f"{task.task_id}.json"
        path.write_text(dumps_json(task), encoding="utf-8")

    def append_event(self, event: Event) -> None:
        path = self.events_dir / f"{event.task_id}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(dumps_json(event) + "\n")

    def load_snapshot(self, task_id: str) -> Optional[Task]:
        path = self.tasks_dir / f"{task_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Task(**data)
