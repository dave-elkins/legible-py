from __future__ import annotations

import logging
import time
from typing import Dict, List, Set, Tuple

from typing_extensions import Protocol, runtime_checkable

from .models import Action

logger = logging.getLogger("wysiwid.store")


@runtime_checkable
class FlowStore(Protocol):
    async def add_action(self, action: Action) -> List[Action]:
        ...

    async def get_history(self, flow_token: str) -> List[Action]:
        ...

    async def record_sync_edge(
        self, from_action_id: str, sync_name: str, to_action_id: str
    ) -> bool:
        ...

    async def evict_flow(self, flow_token: str) -> None:
        ...


class InMemoryFlowStore:
    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._history: Dict[str, List[Action]] = {}
        self._last_write: Dict[str, float] = {}
        self._sync_edges: Set[Tuple[str, str]] = set()
        self._ttl = ttl_seconds

    async def add_action(self, action: Action) -> List[Action]:
        now = time.monotonic()
        token = action.flow_token
        if token not in self._history:
            self._history[token] = []
        self._history[token].append(action)
        self._last_write[token] = now
        self._evict_expired(now)
        return list(self._history.get(token, []))

    async def get_history(self, flow_token: str) -> List[Action]:
        return list(self._history.get(flow_token, []))

    async def record_sync_edge(
        self, from_action_id: str, sync_name: str, to_action_id: str
    ) -> bool:
        key = (from_action_id, sync_name)
        if key in self._sync_edges:
            return False
        self._sync_edges.add(key)
        return True

    async def evict_flow(self, flow_token: str) -> None:
        self._history.pop(flow_token, None)
        self._last_write.pop(flow_token, None)
        logger.debug(f"[InMemoryFlowStore] Evicted flow {flow_token[:8]}…")

    def _evict_expired(self, now: float) -> None:
        expired = [
            token for token, ts in self._last_write.items()
            if now - ts > self._ttl
        ]
        for token in expired:
            self._history.pop(token, None)
            self._last_write.pop(token, None)
        if expired:
            logger.debug(f"[InMemoryFlowStore] TTL-evicted {len(expired)} flow(s).")
