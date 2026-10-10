from __future__ import annotations

import asyncio
from collections import deque


class InMemoryRunQueue:
    """Development queue with duplicate suppression; production can replace this port."""

    def __init__(self) -> None:
        self._items: deque[str] = deque()
        self._queued: set[str] = set()
        self._lock = asyncio.Lock()

    async def enqueue(self, agent_run_id: str) -> None:
        if not agent_run_id.strip():
            raise ValueError("agent_run_id is required.")
        async with self._lock:
            if agent_run_id in self._queued:
                return
            self._items.append(agent_run_id)
            self._queued.add(agent_run_id)

    async def dequeue(self) -> str | None:
        async with self._lock:
            if not self._items:
                return None
            run_id = self._items.popleft()
            self._queued.remove(run_id)
            return run_id

    async def acknowledge(self, agent_run_id: str) -> None:
        _ = agent_run_id

    async def size(self) -> int:
        async with self._lock:
            return len(self._items)
