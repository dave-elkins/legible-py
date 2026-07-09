from __future__ import annotations

import asyncio
import uuid

import pytest

from examples.concepts_pure.billing import BillingState
from examples.concepts_pure.billing import charge as bill_charge
from examples.concepts_pure.inventory import InventoryState
from examples.concepts_pure.inventory import check as inv_check
from examples.concepts_pure.order import OrderState
from examples.concepts_pure.order import create as ord_create
from examples.concepts_pure.web import WebState
from examples.concepts_pure.web import respond as web_respond
from examples.petstore.syncs.purchase import get_purchase_rules
from legible.engine import (
    Action,
    FlowGateway,
    HttpTrigger,
    InMemoryBus,
    InMemoryFlowStore,
    InMemoryStateStore,
    PureFunctionDispatcher,
    SyncEngine,
    TriggerError,
)


class TestPureConceptsInIsolation:

    def test_inventory_check_available(self):
        state = InventoryState()
        new_state, outputs = inv_check(state, {"pet_id": "pet_1"})
        assert outputs == {"available": True, "price": 250.0}
        assert new_state is state

    def test_inventory_check_unavailable(self):
        state = InventoryState()
        new_state, outputs = inv_check(state, {"pet_id": "pet_2"})
        assert outputs == {"available": False, "price": 0.0}

    def test_inventory_check_unknown_pet_returns_error(self):
        state = InventoryState()
        new_state, outputs = inv_check(state, {"pet_id": "pet_3"})
        assert "error" in outputs
        assert new_state is state

    def test_inventory_check_does_not_mutate_state(self):
        state = InventoryState()
        original_catalogue = dict(state.catalogue)
        inv_check(state, {"pet_id": "pet_1"})
        assert state.catalogue == original_catalogue

    def test_inventory_custom_state(self):
        from examples.concepts_pure.inventory import Pet
        state = InventoryState(catalogue={"rare_1": Pet(available=True, price=9999.0)})
        _, outputs = inv_check(state, {"pet_id": "rare_1"})
        assert outputs["available"] is True
        assert outputs["price"] == 9999.0

    def test_order_create_returns_order_id(self):
        state = OrderState()
        new_state, outputs = ord_create(state, {
            "pet_id": "pet_1",
            "customer_id": "alice",
            "amount": 250.0,
        })
        assert outputs["order_id"] == "ord_0001"
        assert outputs["status"] == "pending"

    def test_order_create_increments_counter(self):
        state = OrderState()
        state1, _ = ord_create(state, {"pet_id": "p1", "customer_id": "a", "amount": 1.0})
        state2, out2 = ord_create(state1, {"pet_id": "p2", "customer_id": "b", "amount": 2.0})
        assert out2["order_id"] == "ord_0002"
        assert len(state2.orders) == 2

    def test_order_create_is_deterministic(self):
        state = OrderState()
        _, out1 = ord_create(state, {"pet_id": "p", "customer_id": "c", "amount": 1.0})
        _, out2 = ord_create(state, {"pet_id": "p", "customer_id": "c", "amount": 1.0})
        assert out1 == out2

    def test_order_original_state_not_mutated(self):
        state = OrderState()
        new_state, _ = ord_create(state, {"pet_id": "p", "customer_id": "c", "amount": 1.0})
        assert len(state.orders) == 0
        assert len(new_state.orders) == 1

    def test_billing_charge_returns_receipt(self):
        state = BillingState()
        new_state, outputs = bill_charge(state, {"order_id": "ord_0001", "amount": 250.0})
        assert outputs["status"] == "paid"
        assert outputs["receipt_id"] == "rcpt_0001"

    def test_billing_charge_increments_receipt(self):
        state = BillingState()
        s1, _ = bill_charge(state, {"order_id": "o1", "amount": 1.0})
        s2, out2 = bill_charge(s1, {"order_id": "o2", "amount": 2.0})
        assert out2["receipt_id"] == "rcpt_0002"

    def test_billing_original_state_not_mutated(self):
        state = BillingState()
        new_state, _ = bill_charge(state, {"order_id": "o", "amount": 1.0})
        assert len(state.charges) == 0
        assert len(new_state.charges) == 1

    def test_web_respond_is_stateless(self):
        state = WebState()
        new_state, outputs = web_respond(state, {"status": 200, "message": "ok"})
        assert new_state is state
        assert outputs["delivered"] is True
        assert outputs["status"] == 200


class TestInMemoryStateStore:

    @pytest.mark.asyncio
    async def test_get_returns_initial_state(self):
        store = InMemoryStateStore(InventoryState())
        state = await store.get()
        assert isinstance(state, InventoryState)

    @pytest.mark.asyncio
    async def test_set_then_get_returns_new_state(self):
        from examples.concepts_pure.inventory import Pet
        store = InMemoryStateStore(InventoryState())
        new_state = InventoryState(catalogue={"x": Pet(True, 1.0)})
        await store.set(new_state)
        retrieved = await store.get()
        assert "x" in retrieved.catalogue

    @pytest.mark.asyncio
    async def test_get_returns_deep_copy(self):
        store = InMemoryStateStore(OrderState())
        state1 = await store.get()
        state1.orders["injected"] = "tampered"
        state2 = await store.get()
        assert "injected" not in state2.orders


class TestPureFunctionDispatcher:

    @pytest.mark.asyncio
    async def test_dispatch_calls_handler_and_publishes_completion(self):
        bus = InMemoryBus()
        published = []

        async def observer(action: Action):
            published.append(action)

        await bus.subscribe(observer)

        dispatcher = PureFunctionDispatcher(bus)
        dispatcher.register_concept(
            namespace="Inventory/check",
            handler=inv_check,
            state_store=InMemoryStateStore(InventoryState()),
        )

        action = Action(
            namespace="Inventory/check",
            inputs={"pet_id": "pet_1"},
            flow_token=uuid.uuid4().hex,
        )
        await dispatcher.dispatch(action)
        await asyncio.sleep(0.05)

        completions = [a for a in published if a.outputs is not None]
        assert len(completions) == 1
        assert completions[0].outputs == {"available": True, "price": 250.0}

    @pytest.mark.asyncio
    async def test_state_is_persisted_between_calls(self):
        bus = InMemoryBus()
        store = InMemoryStateStore(OrderState())
        dispatcher = PureFunctionDispatcher(bus)
        dispatcher.register_concept(
            namespace="Order/create",
            handler=ord_create,
            state_store=store,
        )

        async def _dispatch(pet_id):
            a = Action(
                namespace="Order/create",
                inputs={"pet_id": pet_id, "customer_id": "alice", "amount": 10.0},
                flow_token=uuid.uuid4().hex,
            )
            await dispatcher.dispatch(a)
            await asyncio.sleep(0.05)

        await _dispatch("p1")
        await _dispatch("p2")

        final_state = await store.get()
        assert len(final_state.orders) == 2
        assert final_state.next_id == 3

    @pytest.mark.asyncio
    async def test_unknown_namespace_silently_skipped(self):
        bus = InMemoryBus()
        published = []
        await bus.subscribe(lambda a: published.append(a) or asyncio.sleep(0))

        dispatcher = PureFunctionDispatcher(bus)
        action = Action(
            namespace="Unknown/action",
            inputs={},
            flow_token=uuid.uuid4().hex,
        )
        await dispatcher.dispatch(action)
        await asyncio.sleep(0.05)
        completions = [a for a in published if a.outputs is not None]
        assert completions == []

    def test_register_async_handler_raises(self):
        bus = InMemoryBus()
        dispatcher = PureFunctionDispatcher(bus)

        async def bad_handler(state, inputs):
            return state, {}

        with pytest.raises(TypeError, match="synchronous pure function"):
            dispatcher.register_concept(
                namespace="X/op",
                handler=bad_handler,
                state_store=InMemoryStateStore({}),
            )

    @pytest.mark.asyncio
    async def test_concept_error_published_as_error_output(self):
        def failing_handler(state, inputs):
            raise ValueError("something went wrong")

        bus = InMemoryBus()
        published = []

        async def observer(a: Action):
            published.append(a)

        await bus.subscribe(observer)

        dispatcher = PureFunctionDispatcher(bus)
        dispatcher.register_concept(
            namespace="X/op",
            handler=failing_handler,
            state_store=InMemoryStateStore({}),
        )

        action = Action(namespace="X/op", inputs={}, flow_token=uuid.uuid4().hex)
        await dispatcher.dispatch(action)
        await asyncio.sleep(0.05)

        completions = [a for a in published if a.outputs is not None]
        assert completions[0].outputs == {"error": "something went wrong"}


class TestPureEndToEnd:

    async def _boot(self):
        bus = InMemoryBus()
        store = InMemoryFlowStore()
        gateway = FlowGateway(bus, terminal_namespace="Web/respond")

        dispatcher = PureFunctionDispatcher(bus)
        dispatcher.register_concept(
            "Inventory/check",
            inv_check,
            InMemoryStateStore(InventoryState()),
        )
        dispatcher.register_concept(
            "Order/create",
            ord_create,
            InMemoryStateStore(OrderState()),
        )
        dispatcher.register_concept(
            "Billing/charge",
            bill_charge,
            InMemoryStateStore(BillingState()),
        )
        dispatcher.register_concept(
            "Web/respond",
            web_respond,
            InMemoryStateStore(WebState()),
        )

        engine = SyncEngine(bus, store, dispatcher, get_purchase_rules())
        await engine.start()
        await gateway.listen()
        return gateway

    @pytest.mark.asyncio
    async def test_successful_purchase(self):
        gateway = await self._boot()
        trigger = HttpTrigger(
            gateway=gateway,
            namespace="Web/purchase_request",
            error_map={404: lambda r: r.get("status") == 404},
        )
        result = await trigger.fire({"pet_id": "pet_1", "customer_id": "alice"})
        assert result["status"] == 200
        assert "receipt" in result
        assert result["receipt"] == "rcpt_0001"

    @pytest.mark.asyncio
    async def test_out_of_stock(self):
        gateway = await self._boot()
        trigger = HttpTrigger(
            gateway=gateway,
            namespace="Web/purchase_request",
            error_map={404: lambda r: r.get("status") == 404},
        )
        with pytest.raises(TriggerError) as exc_info:
            await trigger.fire({"pet_id": "pet_2", "customer_id": "bob"})
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unknown_pet_returns_error(self):
        gateway = await self._boot()
        trigger = HttpTrigger(gateway=gateway, namespace="Web/purchase_request")
        with pytest.raises(RuntimeError, match="not found in catalogue"):
            await trigger.fire({"pet_id": "pet_3", "customer_id": "charlie"})

    @pytest.mark.asyncio
    async def test_receipt_ids_are_deterministic_across_calls(self):
        gateway = await self._boot()
        trigger = HttpTrigger(
            gateway=gateway,
            namespace="Web/purchase_request",
            error_map={404: lambda r: r.get("status") == 404},
        )
        r1 = await trigger.fire({"pet_id": "pet_1", "customer_id": "alice"})
        assert r1["receipt"] == "rcpt_0001"

    @pytest.mark.asyncio
    async def test_state_accumulates_across_flows(self):
        bus = InMemoryBus()
        store_flow = InMemoryFlowStore()
        gateway = FlowGateway(bus, terminal_namespace="Web/respond")

        order_store = InMemoryStateStore(OrderState())
        billing_store = InMemoryStateStore(BillingState())

        dispatcher = PureFunctionDispatcher(bus)
        dispatcher.register_concept("Inventory/check", inv_check,
                                    InMemoryStateStore(InventoryState()))
        dispatcher.register_concept("Order/create", ord_create, order_store)
        dispatcher.register_concept("Billing/charge", bill_charge, billing_store)
        dispatcher.register_concept("Web/respond", web_respond,
                                    InMemoryStateStore(WebState()))

        engine = SyncEngine(bus, store_flow, dispatcher, get_purchase_rules())
        await engine.start()
        await gateway.listen()

        trigger = HttpTrigger(
            gateway=gateway,
            namespace="Web/purchase_request",
            error_map={404: lambda r: r.get("status") == 404},
        )

        await trigger.fire({"pet_id": "pet_1", "customer_id": "alice"})
        await trigger.fire({"pet_id": "pet_1", "customer_id": "bob"})

        orders = await order_store.get()
        billing = await billing_store.get()

        assert len(orders.orders) == 2
        assert orders.next_id == 3
        assert len(billing.charges) == 2
        assert billing.next_receipt == 3
