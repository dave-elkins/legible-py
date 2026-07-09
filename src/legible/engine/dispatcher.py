from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict

from .models import Action

logger = logging.getLogger("wysiwid.dispatcher")


class AppDispatcher:
    def __init__(self, bus) -> None:
        self.bus = bus
        self._handlers: Dict[str, Callable] = {}

    def register_action(
        self, namespace: str, handler: Callable[[Dict[str, Any]], Any]
    ) -> None:
        self._handlers[namespace] = handler

    async def dispatch(self, action: Action) -> None:
        await self.bus.publish(action)

        handler = self._handlers.get(action.namespace)
        if handler is None:
            logger.debug(f"[Dispatcher] No handler for '{action.namespace}' — skipping.")
            return

        try:
            result = handler(action.inputs)
            if asyncio.iscoroutine(result):
                outputs = await result
            else:
                outputs = result
            logger.info(f"   [Concept] {action.namespace} → {outputs}")
        except Exception as e:
            outputs = {"error": str(e)}
            logger.warning(f"   [Concept] {action.namespace} raised: {e}")

        completion = Action(
            namespace=action.namespace,
            inputs=action.inputs,
            outputs=outputs,
            flow_token=action.flow_token,
            caused_by_sync=action.caused_by_sync,
        )
        await self.bus.publish(completion)


class FlowGateway:
    def __init__(self, bus, terminal_namespace: str = "Web/respond") -> None:
        self.bus = bus
        self.terminal_namespace = terminal_namespace
        self._futures: Dict[str, asyncio.Future] = {}
        self._running = False

    async def listen(self) -> None:
        if not self._running:
            await self.bus.subscribe(self._on_action)
            self._running = True

    async def ask(
        self, root: Action, timeout: float = 5.0
    ) -> Dict[str, Any]:
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._futures[root.flow_token] = future
        await self.bus.publish(root)
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError as e:
            self._futures.pop(root.flow_token, None)
            raise asyncio.TimeoutError(
                f"Flow {root.flow_token[:8]}… timed out after {timeout}s"
            ) from e

    async def _on_action(self, action: Action) -> None:
        if action.outputs and "error" in action.outputs:
            future = self._futures.pop(action.flow_token, None)
            if future is not None and not future.done():
                future.set_exception(RuntimeError(action.outputs["error"]))
            return
        if action.namespace == self.terminal_namespace and action.outputs is None:
            future = self._futures.pop(action.flow_token, None)
            if future is not None and not future.done():
                future.set_result(action.inputs)
