from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from examples.petstore.concepts.billing import charge as billing_charge
from examples.petstore.concepts.inventory import check as inventory_check
from examples.petstore.concepts.order import create as order_create
from examples.petstore.concepts.web import respond as web_respond
from examples.petstore.syncs.purchase import get_purchase_rules
from legible.engine import (
    AppDispatcher,
    AsyncLlmTrigger,
    FlowGateway,
    HttpTrigger,
    InMemoryBus,
    SQLiteFlowStore,
    SyncEngine,
    TriggerError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | [%(levelname)s] | %(message)s",
)
logger = logging.getLogger("wysiwid")

DB_PATH = os.environ.get("LEGIBLE_DB", "legible.db")

bus = InMemoryBus()
dispatcher = AppDispatcher(bus)
gateway = FlowGateway(bus, terminal_namespace="Web/respond")
flow_store = None

purchase_trigger = HttpTrigger(
    gateway=gateway,
    namespace="Web/purchase_request",
    error_map={404: lambda r: r.get("status") == 404},
)

llm_trigger = AsyncLlmTrigger(
    bus=bus,
    namespace="Llm/response",
    terminal_namespace="Web/respond",
    on_complete=lambda flow_token, result: logger.info(
        f"[LLM flow {flow_token[:8]}...] complete: {result}"
    ),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global flow_store
    logger.info("=== Booting Pet Store (SQLite backend) ===")

    flow_store = await SQLiteFlowStore.create(DB_PATH)

    dispatcher.register_action("Inventory/check", inventory_check)
    dispatcher.register_action("Order/create", order_create)
    dispatcher.register_action("Billing/charge", billing_charge)
    dispatcher.register_action("Web/respond", web_respond)

    engine = SyncEngine(bus, flow_store, dispatcher, get_purchase_rules())
    await engine.start()
    await gateway.listen()

    logger.info(f"=== Ready — persisting to {DB_PATH!r} ===")
    yield

    await flow_store.close()
    logger.info("=== Shutdown complete ===")


app = FastAPI(lifespan=lifespan, title="Pet Store")


class PurchaseRequest(BaseModel):
    pet_id: str
    customer_id: str


class LlmPayload(BaseModel):
    conversation_id: str
    text: str


@app.post("/purchase")
async def purchase_pet(request: PurchaseRequest):
    try:
        return await purchase_trigger.fire(request.model_dump())
    except TriggerError as e:
        raise HTTPException(status_code=e.status_code, detail=e.result)
    except (RuntimeError, asyncio.TimeoutError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/llm/response")
async def receive_llm_response(payload: LlmPayload):
    flow_token = await llm_trigger.emit(payload.model_dump())
    return {"flow_token": flow_token, "status": "accepted"}


@app.get("/trace/{flow_token}")
async def get_trace(flow_token: str):
    if flow_store is None:
        raise HTTPException(status_code=503, detail="Store not initialised")

    history = await flow_store.get_any_history(flow_token)
    if not history:
        return {
            "flow_token": flow_token,
            "status": "completed_or_unknown",
            "note": "Action records evicted on flow close. Sync edges retained.",
        }

    return {
        "flow_token": flow_token,
        "action_count": len(history),
        "actions": [
            {
                "id": a.id[:8],
                "namespace": a.namespace,
                "inputs": a.inputs,
                "outputs": a.outputs,
                "caused_by_sync": a.caused_by_sync,
            }
            for a in history
        ],
    }


if __name__ == "__main__":
    uvicorn.run("examples.petstore.app:app", host="0.0.0.0", port=8000, reload=True)
