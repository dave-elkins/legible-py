import asyncio
import uuid


async def check(inputs: dict) -> dict:
    await asyncio.sleep(0.01)
    return {"available": True, "price": 250.0}


async def create(inputs: dict) -> dict:
    await asyncio.sleep(0.01)
    return {"order_id": uuid.uuid4().hex, "status": "pending"}
