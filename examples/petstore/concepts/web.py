from __future__ import annotations


async def respond(inputs: dict) -> dict:
    return {"delivered": True, "status": inputs.get("status", 200)}
