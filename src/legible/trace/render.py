from __future__ import annotations

import json
from typing import List

from .model import FlowTrace, TraceNode

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"


def _concept_colour(namespace: str, use_colour: bool) -> str:
    if not use_colour:
        return namespace
    if "/" in namespace:
        concept, _, action = namespace.partition("/")
        return f"{_BOLD}{_CYAN}{concept}{_RESET}/{action}"
    return f"{_BOLD}{_CYAN}{namespace}{_RESET}"


def _outputs_summary(outputs: dict | None, use_colour: bool, max_len: int = 60) -> str:
    if outputs is None:
        return ""
    if not outputs:
        return "{}"
    parts = [f"{k}={_summarise_val(v)}" for k, v in outputs.items()]
    raw = "  \u2192  " + "  ".join(parts)
    if len(raw) > max_len:
        raw = raw[:max_len - 1] + "..."
    if use_colour:
        return f"{_DIM}{raw}{_RESET}"
    return raw


def _summarise_val(v) -> str:
    if isinstance(v, str) and len(v) > 20:
        return v[:18] + "..."
    return str(v)


def _sync_label(sync_name: str | None, use_colour: bool) -> str:
    if sync_name is None:
        return ""
    label = f"[{sync_name}]"
    if use_colour:
        return f"{_YELLOW}{label}{_RESET}"
    return label


def render_tree(trace: FlowTrace, use_colour: bool = True) -> str:
    lines: List[str] = []

    header = (
        f"Flow {trace.flow_token[:8]}  "
        f"\u2502  {trace.action_count} action(s)  "
        f"\u2502  depth {trace.max_depth}"
    )
    if use_colour:
        header = f"{_BOLD}{header}{_RESET}"
    lines.append(header)

    _render_node(trace.root, lines, prefix="", is_last=True, use_colour=use_colour)
    return "\n".join(lines)


def _render_node(
    node: TraceNode,
    lines: List[str],
    prefix: str,
    is_last: bool,
    use_colour: bool,
) -> None:
    connector = "\u2514\u2500\u2500" if is_last else "\u251c\u2500\u2500"
    if node.caused_by_sync is not None:
        sync_indent = prefix + ("    " if is_last else "\u2502   ")
        label = _sync_label(node.caused_by_sync, use_colour)
        lines.append(f"{sync_indent}\u21b3 {label}")

    namespace_str = _concept_colour(node.namespace, use_colour)
    outputs_str = _outputs_summary(node.outputs, use_colour)
    bullet = "\u25cf"
    if use_colour and node.caused_by_sync is None:
        bullet = f"{_GREEN}\u25cf{_RESET}"

    lines.append(f"{prefix}{connector}{bullet}  {namespace_str}{outputs_str}")

    child_prefix = prefix + ("    " if is_last else "\u2502   ")
    for i, child in enumerate(node.children):
        child_is_last = (i == len(node.children) - 1)
        _render_node(child, lines, child_prefix, child_is_last, use_colour)


def render_json(trace: FlowTrace, indent: int = 2) -> str:
    return json.dumps(trace.to_dict(), indent=indent)
