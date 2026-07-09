from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

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
    InMemoryFlowStore,
    SyncEngine,
    TriggerError,
)

ROOT = os.path.join(os.path.dirname(__file__), "..")


async def _boot_stack():
    bus = InMemoryBus()
    store = InMemoryFlowStore()
    dispatcher = AppDispatcher(bus)
    gateway = FlowGateway(bus, terminal_namespace="Web/respond")

    dispatcher.register_action("Inventory/check", inventory_check)
    dispatcher.register_action("Order/create", order_create)
    dispatcher.register_action("Billing/charge", billing_charge)
    dispatcher.register_action("Web/respond", web_respond)

    engine = SyncEngine(bus, store, dispatcher, get_purchase_rules())
    await engine.start()
    await gateway.listen()

    return bus, gateway, dispatcher


class TestPurchaseFlows:

    @pytest.mark.asyncio
    async def test_successful_purchase(self):
        bus, gateway, _ = await _boot_stack()
        trigger = HttpTrigger(
            gateway=gateway,
            namespace="Web/purchase_request",
            error_map={404: lambda r: r.get("status") == 404},
        )
        result = await trigger.fire({"pet_id": "pet_1", "customer_id": "alice"})
        assert result["status"] == 200
        assert "receipt" in result
        assert result["receipt"].startswith("rcpt_")

    @pytest.mark.asyncio
    async def test_out_of_stock_raises_trigger_error(self):
        bus, gateway, _ = await _boot_stack()
        trigger = HttpTrigger(
            gateway=gateway,
            namespace="Web/purchase_request",
            error_map={404: lambda r: r.get("status") == 404},
        )
        with pytest.raises(TriggerError) as exc_info:
            await trigger.fire({"pet_id": "pet_2", "customer_id": "bob"})
        assert exc_info.value.status_code == 404
        assert "out of stock" in exc_info.value.result["message"]

    @pytest.mark.asyncio
    async def test_infrastructure_error_raises_runtime_error(self):
        bus, gateway, _ = await _boot_stack()
        trigger = HttpTrigger(
            gateway=gateway,
            namespace="Web/purchase_request",
        )
        with pytest.raises(RuntimeError, match="Database cluster unreachable"):
            await trigger.fire({"pet_id": "pet_3", "customer_id": "charlie"})


class TestConceptsInIsolation:

    @pytest.mark.asyncio
    async def test_inventory_check_available(self):
        result = await inventory_check({"pet_id": "pet_1"})
        assert result == {"available": True, "price": 250.0}

    @pytest.mark.asyncio
    async def test_inventory_check_unavailable(self):
        result = await inventory_check({"pet_id": "pet_2"})
        assert result == {"available": False, "price": 0.0}

    @pytest.mark.asyncio
    async def test_inventory_check_error(self):
        with pytest.raises(ConnectionError):
            await inventory_check({"pet_id": "pet_3"})

    @pytest.mark.asyncio
    async def test_order_create_returns_order_id(self):
        result = await order_create({"pet_id": "pet_1", "customer_id": "alice", "amount": 250.0})
        assert "order_id" in result
        assert result["order_id"].startswith("ord_")
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_billing_charge_returns_receipt(self):
        result = await billing_charge({"order_id": "ord_abc", "amount": 250.0})
        assert result["status"] == "paid"
        assert result["receipt_id"].startswith("rcpt_")

    @pytest.mark.asyncio
    async def test_web_respond_returns_delivered(self):
        result = await web_respond({"status": 200, "message": "ok"})
        assert result["delivered"] is True
        assert result["status"] == 200


class TestLlmTrigger:

    @pytest.mark.asyncio
    async def test_llm_flow_completes_and_fires_callback(self):
        bus, gateway, _ = await _boot_stack()
        completed = {}

        llm_trigger = AsyncLlmTrigger(
            bus=bus,
            namespace="Llm/response",
            terminal_namespace="Web/respond",
            on_complete=lambda ft, r: completed.update({ft: r}),
        )

        flow_token = await llm_trigger.emit({
            "conversation_id": "conv_42",
            "text": "Here is your pet recommendation.",
        })

        await asyncio.sleep(0.3)

        assert flow_token in completed
        result = completed[flow_token]
        assert result["status"] == 200
        assert result["source"] == "llm"
        assert result["conversation_id"] == "conv_42"

    @pytest.mark.asyncio
    async def test_llm_flow_token_distinct_per_emit(self):
        bus, gateway, _ = await _boot_stack()
        llm_trigger = AsyncLlmTrigger(bus=bus, namespace="Llm/response")

        t1 = await llm_trigger.emit({"conversation_id": "c1", "text": "a"})
        t2 = await llm_trigger.emit({"conversation_id": "c2", "text": "b"})
        assert t1 != t2


class TestCliEntryPoint:

    def test_cli_successful_purchase(self, capsys):
        from examples.petstore.cli import main as cli_main
        sys.argv = ["cli", "pet_1", "alice"]
        cli_main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["status"] == 200
        assert "receipt" in result

    def test_cli_out_of_stock(self, capsys):
        from examples.petstore.cli import main as cli_main
        sys.argv = ["cli", "pet_2", "bob"]
        cli_main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["status"] == 404
