from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WebState:
    pass


def respond(
    state: WebState,
    inputs: dict,
) -> tuple[WebState, dict]:
    return state, {"delivered": True, "status": inputs.get("status", 200)}
