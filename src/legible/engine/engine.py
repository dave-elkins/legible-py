from __future__ import annotations

import logging
from typing import List

from .models import Action, Matcher, SyncRule, Var

logger = logging.getLogger("wysiwid.engine")


class SyncEngine:
    def __init__(
        self,
        bus,
        flow_store,
        dispatcher,
        rules: List[SyncRule],
        terminal_namespace: str = "Web/respond",
    ) -> None:
        self.bus = bus
        self.flow_store = flow_store
        self.dispatcher = dispatcher
        self.rules = rules
        self.terminal_namespace = terminal_namespace

    async def start(self) -> None:
        await self.bus.subscribe(self._process_action)

    async def _process_action(self, action: Action) -> None:
        if action.outputs is None:
            return

        history = await self.flow_store.add_action(action)
        logger.info(
            f"[Engine] Completion: {action.namespace} "
            f"(flow={action.flow_token[:8]}…)"
        )

        for rule in self.rules:
            result = Matcher.match_when(rule.when, history, action.flow_token)
            if result is None:
                continue

            bindings, matched_ids = result

            match_key = "__".join(sorted(matched_ids))
            newly_recorded = await self.flow_store.record_sync_edge(
                from_action_id=match_key,
                sync_name=rule.name,
                to_action_id=action.id,
            )
            if not newly_recorded:
                continue

            logger.info(f" -> [Matched] '{rule.name}' bindings={bindings}")

            frames = [bindings]
            for condition in rule.where:
                new_frames = []
                for frame in frames:
                    res = condition(frame)
                    if isinstance(res, list):
                        new_frames.extend(res)
                    elif res is not None:
                        new_frames.append(res)
                frames = new_frames
                if not frames:
                    break

            for frame in frames:
                for then_pattern in rule.then:
                    resolved_inputs = {
                        k: frame[v.name] if isinstance(v, Var) else v
                        for k, v in then_pattern.inputs.items()
                    }
                    new_action = Action(
                        namespace=then_pattern.namespace,
                        inputs=resolved_inputs,
                        outputs=None,
                        flow_token=action.flow_token,
                        caused_by_sync=rule.name,
                    )
                    logger.info(
                        f"    -> [Invoke] {new_action.namespace} {resolved_inputs}"
                    )
                    await self.dispatcher.dispatch(new_action)

        if action.namespace == self.terminal_namespace:
            await self.flow_store.evict_flow(action.flow_token)
            logger.debug(
                f"[Engine] Flow {action.flow_token[:8]}… closed at terminal action."
            )
