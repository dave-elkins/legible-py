from __future__ import annotations

import asyncio
import uuid


async def create(inputs: dict) -> dict:
    await asyncio.sleep(0.05)
    order_id = f"ord_{uuid.uuid4().hex[:6]}"
    return {"order_id": order_id, "status": "pending"}
