from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from typing import Any, Callable, Dict, List, Optional

from typing_extensions import Protocol, runtime_checkable

from .bus import InMemoryBus
from .dispatcher import FlowGateway
from .models import Action

logger = logging.getLogger("wysiwid.triggers")


@runtime_checkable
class Trigger(Protocol):
    async def fire(self, payload: Dict[str, Any], timeout: float = 5.0) -> Dict[str, Any]:
        ...


@runtime_checkable
class AsyncTrigger(Protocol):
    async def emit(self, payload: Dict[str, Any]) -> str:
        ...


class HttpTrigger:
    def __init__(
        self,
        gateway: FlowGateway,
        namespace: str,
        error_map: Optional[Dict[int, Callable[[dict], bool]]] = None,
    ) -> None:
        self.gateway = gateway
        self.namespace = namespace
        self.error_map = error_map or {}

    async def fire(
        self, payload: Dict[str, Any], timeout: float = 5.0
    ) -> Dict[str, Any]:
        root = Action(
            namespace=self.namespace,
            inputs=payload,
            outputs={"received": True},
            flow_token=uuid.uuid4().hex,
        )
        result = await self.gateway.ask(root, timeout=timeout)

        for status_code, predicate in self.error_map.items():
            if predicate(result):
                raise TriggerError(status_code=status_code, result=result)

        return result


class CliTrigger:
    def __init__(
        self,
        bus: InMemoryBus,
        gateway: FlowGateway,
        namespace: str,
        engine_starters: Optional[List] = None,
    ) -> None:
        self.bus = bus
        self.gateway = gateway
        self.namespace = namespace
        self.engine_starters = engine_starters or []

    def run(self, payload: Optional[Dict[str, Any]] = None, timeout: float = 5.0) -> None:
        asyncio.run(self._run_async(payload or {}, timeout))

    async def _run_async(self, payload: Dict[str, Any], timeout: float) -> None:
        for starter in self.engine_starters:
            await starter()

        root = Action(
            namespace=self.namespace,
            inputs=payload,
            outputs={"received": True},
            flow_token=uuid.uuid4().hex,
        )
        try:
            result = await self.gateway.ask(root, timeout=timeout)
            print(json.dumps(result, indent=2))
        except RuntimeError as e:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
            sys.exit(1)
        except asyncio.TimeoutError:
            print(json.dumps({"error": "timeout"}), file=sys.stderr)
            sys.exit(1)


class AsyncLlmTrigger:
    def __init__(
        self,
        bus: InMemoryBus,
        namespace: str,
        terminal_namespace: str = "Web/respond",
        on_complete: Optional[Callable[[str, dict], Any]] = None,
    ) -> None:
        self.bus = bus
        self.namespace = namespace
        self.terminal_namespace = terminal_namespace
        self.on_complete = on_complete
        self._subscribed = False

    async def _ensure_subscribed(self) -> None:
        if not self._subscribed:
            await self.bus.subscribe(self._observe)
            self._subscribed = True

    async def _observe(self, action: Action) -> None:
        if (
            self.on_complete
            and action.namespace == self.terminal_namespace
            and action.outputs is None
        ):
            result = action.inputs
            try:
                coro_or_val = self.on_complete(action.flow_token, result)
                if asyncio.iscoroutine(coro_or_val):
                    await coro_or_val
            except Exception as e:
                logger.warning(f"[AsyncLlmTrigger] on_complete raised: {e}")

    async def emit(self, payload: Dict[str, Any]) -> str:
        await self._ensure_subscribed()

        flow_token = uuid.uuid4().hex
        root = Action(
            namespace=self.namespace,
            inputs=payload,
            outputs={"received": True},
            flow_token=flow_token,
        )
        await self.bus.publish(root)
        logger.info(
            f"[AsyncLlmTrigger] Emitted {self.namespace} "
            f"(flow={flow_token[:8]}…)"
        )
        return flow_token


class TriggerError(Exception):
    def __init__(self, status_code: int, result: dict) -> None:
        self.status_code = status_code
        self.result = result
        super().__init__(f"HTTP {status_code}: {result}")
