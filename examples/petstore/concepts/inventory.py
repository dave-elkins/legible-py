from __future__ import annotations

import asyncio


async def check(inputs: dict) -> dict:
    await asyncio.sleep(0.05)
    pet_id = inputs.get("pet_id")

    if pet_id == "pet_3":
        raise ConnectionError("Database cluster unreachable")
    if pet_id == "pet_1":
        return {"available": True, "price": 250.0}
    return {"available": False, "price": 0.0}
