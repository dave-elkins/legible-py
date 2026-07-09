from __future__ import annotations

import asyncio
import uuid


async def charge(inputs: dict) -> dict:
    await asyncio.sleep(0.05)
    receipt_id = f"rcpt_{uuid.uuid4().hex[:6]}"
    return {"status": "paid", "receipt_id": receipt_id}
