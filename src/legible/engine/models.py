from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class Action:
    namespace: str
    inputs: Dict[str, Any]
    flow_token: str
    outputs: Optional[Dict[str, Any]] = None
    caused_by_sync: Optional[str] = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass
class Var:
    name: str

    def __repr__(self) -> str:
        return f"Var({self.name!r})"


@dataclass
class ActionPattern:
    namespace: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Optional[Dict[str, Any]] = None


@dataclass
class SyncRule:
    name: str
    when: List[ActionPattern]
    where: List[Callable[[Dict[str, Any]], List[Dict[str, Any]]]]
    then: List[ActionPattern]


class Sync:
    def __init__(self, name: str) -> None:
        self._name = name
        self._when: List[ActionPattern] = []
        self._where: List[Callable] = []
        self._then: List[ActionPattern] = []

    def when(self, *patterns: ActionPattern) -> "Sync":
        self._when.extend(patterns)
        return self

    def where(self, fn: Callable[[Dict[str, Any]], List[Dict[str, Any]]]) -> "Sync":
        self._where.append(fn)
        return self

    def then(self, *patterns: ActionPattern) -> "Sync":
        self._then.extend(patterns)
        return self

    def build(self) -> SyncRule:
        return SyncRule(
            name=self._name,
            when=list(self._when),
            where=list(self._where),
            then=list(self._then),
        )


class Matcher:
    @staticmethod
    def match_when(
        patterns: List[ActionPattern],
        history: List[Action],
        flow_token: str,
    ) -> Optional[Tuple[Dict[str, Any], List[str]]]:
        history = [a for a in history if a.flow_token == flow_token]
        matched_ids: List[str] = []
        bindings: Dict[str, Any] = {}

        for pattern in patterns:
            matched = None
            for action in history:
                if action.namespace != pattern.namespace:
                    continue
                if action.outputs is None:
                    continue
                if pattern.outputs is not None:
                    if not _match_outputs(action.outputs, pattern.outputs, bindings):
                        continue
                if pattern.inputs:
                    if not _match_inputs(action.inputs, pattern.inputs, bindings):
                        continue
                matched = action
                break

            if matched is None:
                return None
            matched_ids.append(matched.id)

        return bindings, matched_ids


def _match_outputs(
    actual: Dict[str, Any],
    pattern: Dict[str, Any],
    bindings: Dict[str, Any],
) -> bool:
    for key, expected in pattern.items():
        if isinstance(expected, Var):
            bindings[expected.name] = actual.get(key)
        elif actual.get(key) != expected:
            return False
    return True


def _match_inputs(
    actual: Dict[str, Any],
    pattern: Dict[str, Any],
    bindings: Dict[str, Any],
) -> bool:
    for key, expected in pattern.items():
        if isinstance(expected, Var):
            if key not in actual:
                return False
            bindings[expected.name] = actual[key]
        elif actual.get(key) != expected:
            return False
    return True
