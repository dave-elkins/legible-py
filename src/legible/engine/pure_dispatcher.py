from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Tuple

from .models import Action
from .state_store import ConceptStateStore

logger = logging.getLogger("wysiwid.pure_dispatcher")


class PureFunctionDispatcher:
    def __init__(self, bus) -> None:
        self.bus = bus
        self._registry: Dict[str, Tuple[Callable, ConceptStateStore]] = {}

    def register_concept(
        self,
        namespace: str,
        handler: Callable,
        state_store: Any,
    ) -> None:
        if not callable(handler):
            raise TypeError(f"handler for {namespace!r} must be callable")
        import asyncio
        if asyncio.iscoroutinefunction(handler):
            raise TypeError(
                f"handler for {namespace!r} must be a synchronous pure function, "
                f"not an async function. Pure functions have no I/O and no await."
            )
        self._registry[namespace] = (handler, state_store)

    async def dispatch(self, action: Action) -> None:
        await self.bus.publish(action)

        entry = self._registry.get(action.namespace)
        if not entry:
            logger.debug(
                f"[PureDispatcher] No handler for '{action.namespace}' — skipping."
            )
            return

        handler, state_store = entry

        try:
            state = await state_store.get()
            new_state, outputs = handler(state, action.inputs)
            await state_store.set(new_state)
            logger.info(
                f"   [PureConcept] {action.namespace} → {outputs}"
            )
        except Exception as e:
            outputs = {"error": str(e)}
            logger.warning(
                f"   [PureConcept] {action.namespace} raised: {e}"
            )

        completion = Action(
            namespace=action.namespace,
            inputs=action.inputs,
            outputs=outputs,
            flow_token=action.flow_token,
            caused_by_sync=action.caused_by_sync,
        )
        await self.bus.publish(completion)
