from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Dict, List


class SSEBus:
    def __init__(self) -> None:
        self._queues: Dict[str, List[asyncio.Queue]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.setdefault(task_id, []).append(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        if task_id in self._queues and queue in self._queues[task_id]:
            self._queues[task_id].remove(queue)
            if not self._queues[task_id]:
                self._queues.pop(task_id, None)

    async def publish(self, task_id: str, event: Dict[str, Any]) -> None:
        for queue in list(self._queues.get(task_id, [])):
            await queue.put(event)

    async def stream(self, task_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        queue = self.subscribe(task_id)
        try:
            while True:
                item = await queue.get()
                yield item
        finally:
            self.unsubscribe(task_id, queue)
