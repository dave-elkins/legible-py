from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, List

from .models import Action

logger = logging.getLogger("wysiwid.bus")


class InMemoryBus:
    def __init__(self) -> None:
        self._subscribers: List[Callable[[Action], Any]] = []
        self._queue: asyncio.Queue = asyncio.Queue()

    async def subscribe(self, observer: Callable[[Action], Any]) -> None:
        self._subscribers.append(observer)

    async def publish(self, action: Action) -> None:
        for subscriber in self._subscribers:
            asyncio.ensure_future(self._safe_dispatch(subscriber, action))

    async def _safe_dispatch(self, subscriber: Callable, action: Action) -> None:
        try:
            result = subscriber(action)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.warning(f"[Bus] Subscriber raised: {e}")
