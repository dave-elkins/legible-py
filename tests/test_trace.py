from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from legible.engine import (
    Action,
    ActionPattern,
    AppDispatcher,
    FlowGateway,
    HttpTrigger,
    InMemoryBus,
    SQLiteFlowStore,
    Sync,
    SyncEngine,
    Var,
)
from legible.trace import build_trace
from legible.trace.render import render_json, render_tree


def _action(namespace, caused_by=None, outputs=None, flow_token=None):
    return Action(
        namespace=namespace,
        inputs={},
        outputs=outputs if outputs is not None else {"ok": True},
        flow_token=flow_token or uuid.uuid4().hex,
        caused_by_sync=caused_by,
    )


def _linear_flow():
    ft = uuid.uuid4().hex
    return ft, [
        _action("Web/request",    caused_by=None,      flow_token=ft),
        _action("Concept/stepA",  caused_by="SyncA",   flow_token=ft),
        _action("Concept/stepB",  caused_by="SyncB",   flow_token=ft),
        _action("Web/respond",    caused_by="SyncC",   flow_token=ft),
    ]


def _fanout_flow():
    ft = uuid.uuid4().hex
    return ft, [
        _action("Collection/delete", caused_by=None,            flow_token=ft),
        _action("Item/delete",       caused_by="CascadeDelete", flow_token=ft,
                outputs={"item_id": "a"}),
        _action("Item/delete",       caused_by="CascadeDelete", flow_token=ft,
                outputs={"item_id": "b"}),
        _action("Item/delete",       caused_by="CascadeDelete", flow_token=ft,
                outputs={"item_id": "c"}),
    ]


class TestBuildTrace:

    def test_linear_flow_root_identified(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        assert trace.root.namespace == "Web/request"
        assert trace.root.caused_by_sync is None

    def test_linear_flow_correct_chain(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        assert len(trace.root.children) == 1
        step_a = trace.root.children[0]
        assert step_a.namespace == "Concept/stepA"
        assert len(step_a.children) == 1
        step_b = step_a.children[0]
        assert step_b.namespace == "Concept/stepB"
        assert len(step_b.children) == 1
        respond = step_b.children[0]
        assert respond.namespace == "Web/respond"
        assert respond.children == []

    def test_linear_flow_depth(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        assert trace.max_depth == 4

    def test_linear_flow_action_count(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        assert trace.action_count == 4

    def test_fanout_siblings_under_root(self):
        ft, history = _fanout_flow()
        trace = build_trace(ft, history)
        assert trace.root.namespace == "Collection/delete"
        assert len(trace.root.children) == 3
        namespaces = [c.namespace for c in trace.root.children]
        assert all(ns == "Item/delete" for ns in namespaces)

    def test_fanout_depth_is_two(self):
        ft, history = _fanout_flow()
        trace = build_trace(ft, history)
        assert trace.max_depth == 2

    def test_invocations_excluded(self):
        ft = uuid.uuid4().hex
        history = [
            Action(namespace="Web/req", inputs={}, outputs={"ok": True},
                   flow_token=ft, caused_by_sync=None),
            Action(namespace="Concept/op", inputs={}, outputs=None,
                   flow_token=ft, caused_by_sync="SyncX"),
            Action(namespace="Concept/op", inputs={}, outputs={"done": True},
                   flow_token=ft, caused_by_sync="SyncX"),
        ]
        trace = build_trace(ft, history)
        assert trace.action_count == 2

    def test_raises_on_empty_history(self):
        with pytest.raises(ValueError, match="No completion records"):
            build_trace(uuid.uuid4().hex, [])

    def test_raises_on_missing_root(self):
        ft = uuid.uuid4().hex
        history = [
            _action("Concept/op", caused_by="SomeSyncName", flow_token=ft),
        ]
        with pytest.raises(ValueError, match="No root action"):
            build_trace(ft, history)

    def test_to_dict_is_json_serialisable(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        d = trace.to_dict()
        json.dumps(d)
        assert d["flow_token"] == ft
        assert d["action_count"] == 4
        assert "root" in d


class TestRenderTree:

    def test_header_contains_flow_token_prefix(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        output = render_tree(trace, use_colour=False)
        assert ft[:8] in output

    def test_header_contains_action_count(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        output = render_tree(trace, use_colour=False)
        assert "4 action(s)" in output

    def test_header_contains_depth(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        output = render_tree(trace, use_colour=False)
        assert "depth 4" in output

    def test_all_namespaces_appear(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        output = render_tree(trace, use_colour=False)
        for ns in ["Web/request", "Concept/stepA", "Concept/stepB", "Web/respond"]:
            assert ns in output

    def test_sync_labels_appear(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        output = render_tree(trace, use_colour=False)
        for label in ["[SyncA]", "[SyncB]", "[SyncC]"]:
            assert label in output

    def test_no_colour_produces_no_ansi(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        output = render_tree(trace, use_colour=False)
        assert "\033[" not in output

    def test_with_colour_produces_ansi(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        output = render_tree(trace, use_colour=True)
        assert "\033[" in output

    def test_fanout_all_children_appear(self):
        ft, history = _fanout_flow()
        trace = build_trace(ft, history)
        output = render_tree(trace, use_colour=False)
        assert output.count("Item/delete") == 3


class TestRenderJson:

    def test_json_is_valid(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        parsed = json.loads(render_json(trace))
        assert parsed["flow_token"] == ft

    def test_json_root_has_children(self):
        ft, history = _linear_flow()
        trace = build_trace(ft, history)
        parsed = json.loads(render_json(trace))
        assert len(parsed["root"]["children"]) == 1

    def test_json_fanout_root_has_three_children(self):
        ft, history = _fanout_flow()
        trace = build_trace(ft, history)
        parsed = json.loads(render_json(trace))
        assert len(parsed["root"]["children"]) == 3


class TestEndToEnd:

    @pytest.mark.asyncio
    async def test_purchase_flow_trace(self, tmp_path):
        db_path = str(tmp_path / "trace_test.db")

        async def check_inventory(inputs):
            return {"available": True, "price": 99.0}

        async def create_order(inputs):
            return {"order_id": "ord_test", "status": "pending"}

        async def charge_billing(inputs):
            return {"status": "paid", "receipt_id": "rcpt_test"}

        async def web_respond(inputs):
            return {"delivered": True}

        rules = [
            Sync("CheckInventory")
            .when(ActionPattern(
                "Web/purchase_request",
                inputs={"pet_id": Var("pet_id"), "customer_id": Var("cid")},
                outputs={},
            ))
            .then(ActionPattern("Inventory/check", inputs={"pet_id": Var("pet_id")}))
            .build(),
            Sync("PlaceOrder")
            .when(
                ActionPattern(
                    "Web/purchase_request",
                    inputs={"pet_id": Var("pet_id"), "customer_id": Var("cid")},
                    outputs={},
                ),
                ActionPattern(
                    "Inventory/check",
                    inputs={"pet_id": Var("pet_id")},
                    outputs={"available": True, "price": Var("price")},
                ),
            )
            .then(ActionPattern(
                "Order/create",
                inputs={"pet_id": Var("pet_id"), "customer_id": Var("cid"), "amount": Var("price")},
            ))
            .build(),
            Sync("BillCustomer")
            .when(ActionPattern(
                "Order/create",
                inputs={"amount": Var("price")},
                outputs={"order_id": Var("oid")},
            ))
            .then(ActionPattern(
                "Billing/charge",
                inputs={"order_id": Var("oid"), "amount": Var("price")},
            ))
            .build(),
            Sync("SendReceipt")
            .when(ActionPattern(
                "Billing/charge",
                outputs={"status": "paid", "receipt_id": Var("rcpt")},
            ))
            .then(ActionPattern("Web/respond", inputs={"status": 200, "receipt": Var("rcpt")}))
            .build(),
        ]

        store = await SQLiteFlowStore.create(db_path, retain_history=True)
        bus = InMemoryBus()
        dispatcher = AppDispatcher(bus)
        gateway = FlowGateway(bus)

        dispatcher.register_action("Inventory/check", check_inventory)
        dispatcher.register_action("Order/create", create_order)
        dispatcher.register_action("Billing/charge", charge_billing)
        dispatcher.register_action("Web/respond", web_respond)

        engine = SyncEngine(bus, store, dispatcher, rules)
        await engine.start()
        await gateway.listen()

        trigger = HttpTrigger(gateway=gateway, namespace="Web/purchase_request")
        result = await trigger.fire({"pet_id": "pet_1", "customer_id": "alice"})
        assert result["status"] == 200

        await asyncio.sleep(0.1)

        all_flows = await store.get_all_flows(include_completed=True)
        assert len(all_flows) >= 1

        flow_token = all_flows[-1]
        history = await store.get_any_history(flow_token)
        assert len(history) > 0

        trace = build_trace(flow_token, history)

        assert trace.root.namespace == "Web/purchase_request"
        assert trace.max_depth >= 4

        tree_output = render_tree(trace, use_colour=False)
        for ns in ["Inventory/check", "Order/create", "Billing/charge", "Web/respond"]:
            assert ns in tree_output

        for label in ["[CheckInventory]", "[PlaceOrder]", "[BillCustomer]", "[SendReceipt]"]:
            assert label in tree_output

        parsed = json.loads(render_json(trace))
        assert parsed["root"]["namespace"] == "Web/purchase_request"

        await store.close()

    @pytest.mark.asyncio
    async def test_trace_survives_store_reopen(self, tmp_path):
        db_path = str(tmp_path / "reopen_test.db")

        ft = uuid.uuid4().hex
        store1 = await SQLiteFlowStore.create(db_path, retain_history=True)
        history_in = [
            _action("Web/req",    caused_by=None,    flow_token=ft),
            _action("Concept/op", caused_by="SyncX", flow_token=ft),
        ]
        for a in history_in:
            await store1.add_action(a)
        await store1.evict_flow(ft)
        await store1.close()

        store2 = await SQLiteFlowStore.create(db_path, retain_history=True)
        history_out = await store2.get_any_history(ft)
        await store2.close()

        assert len(history_out) == 2
        trace = build_trace(ft, history_out)
        assert trace.root.namespace == "Web/req"
        assert len(trace.root.children) == 1
        assert trace.root.children[0].namespace == "Concept/op"
