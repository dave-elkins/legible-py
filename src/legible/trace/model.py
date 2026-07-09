from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..engine.models import Action


@dataclass
class TraceNode:
    action_id: str
    namespace: str
    inputs: Dict[str, Any]
    outputs: Optional[Dict[str, Any]]
    caused_by_sync: Optional[str]
    children: List["TraceNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "namespace": self.namespace,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "caused_by_sync": self.caused_by_sync,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class FlowTrace:
    flow_token: str
    root: TraceNode
    action_count: int
    max_depth: int

    def to_dict(self) -> dict:
        return {
            "flow_token": self.flow_token,
            "action_count": self.action_count,
            "max_depth": self.max_depth,
            "root": self.root.to_dict(),
        }


def build_trace(flow_token: str, history: List[Action]) -> FlowTrace:
    completions = [a for a in history if a.outputs is not None]

    if not completions:
        raise ValueError(f"No completion records found for flow {flow_token[:8]}...")

    roots = [a for a in completions if a.caused_by_sync is None]
    if not roots:
        raise ValueError(
            f"No root action found for flow {flow_token[:8]}... "
            f"(all {len(completions)} records have caused_by_sync set)"
        )

    root_action = roots[0]

    nodes: Dict[str, TraceNode] = {}
    for action in completions:
        nodes[action.id] = TraceNode(
            action_id=action.id[:8],
            namespace=action.namespace,
            inputs=action.inputs,
            outputs=action.outputs,
            caused_by_sync=action.caused_by_sync,
        )

    for i, action in enumerate(completions):
        if action.caused_by_sync is None:
            continue

        parent_node = None
        for j in range(i - 1, -1, -1):
            candidate = completions[j]
            if candidate.caused_by_sync != action.caused_by_sync:
                parent_node = nodes[candidate.id]
                break

        if parent_node is None:
            parent_node = nodes[root_action.id]

        parent_node.children.append(nodes[action.id])

    root_node = nodes[root_action.id]
    depth = _max_depth(root_node)

    return FlowTrace(
        flow_token=flow_token,
        root=root_node,
        action_count=len(completions),
        max_depth=depth,
    )


def _max_depth(node: TraceNode, current: int = 1) -> int:
    if not node.children:
        return current
    return max(_max_depth(child, current + 1) for child in node.children)
