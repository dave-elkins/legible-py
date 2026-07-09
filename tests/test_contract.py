from __future__ import annotations

import uuid

import pytest

from legible.engine import (
    Action,
    ActionPattern,
    AppDispatcher,
    FlowGateway,
    InMemoryBus,
    InMemoryFlowStore,
    Matcher,
    SQLiteFlowStore,
    Sync,
    SyncEngine,
    Var,
)


async def _make_memory_store():
    return InMemoryFlowStore()


async def _make_sqlite_store():
    return await SQLiteFlowStore.create(":memory:")


STORE_FACTORIES = [
    pytest.param(_make_memory_store, id="memory"),
    pytest.param(_make_sqlite_store, id="sqlite"),
]


def _root_action(namespace="Web/request", **inputs) -> Action:
    return Action(
        namespace=namespace,
        inputs=inputs,
        outputs={"received": True},
        flow_token=uuid.uuid4().hex,
    )


def _completion(namespace, flow_token, caused_by=None, **outputs) -> Action:
    return Action(
        namespace=namespace,
        inputs={},
        outputs=outputs,
        flow_token=flow_token,
        caused_by_sync=caused_by,
    )


class TestFlowIsolation:

    @pytest.mark.parametrize("store_factory", STORE_FACTORIES)
    @pytest.mark.asyncio
    async def test_matcher_ignores_cross_flow_actions(self, store_factory):
        flow_a = uuid.uuid4().hex
        flow_b = uuid.uuid4().hex

        action_a = Action(namespace="Concept/step1", inputs={}, outputs={"x": 1}, flow_token=flow_a)
        action_b = Action(namespace="Concept/step2", inputs={}, outputs={"y": 2}, flow_token=flow_b)

        store = await store_factory()
        await store.add_action(action_a)
        await store.add_action(action_b)

        history = await store.get_history(flow_a) + await store.get_history(flow_b)

        patterns = [
            ActionPattern("Concept/step1", outputs={"x": Var("x")}),
            ActionPattern("Concept/step2", outputs={"y": Var("y")}),
        ]

        result_a = Matcher.match_when(patterns, history, flow_a)
        assert result_a is None, "Cross-flow match must not succeed"

        result_b = Matcher.match_when(patterns, history, flow_b)
        assert result_b is None, "Cross-flow match must not succeed"

    @pytest.mark.parametrize("store_factory", STORE_FACTORIES)
    @pytest.mark.asyncio
    async def test_same_namespace_different_flows_isolated(self, store_factory):
        flow_a = uuid.uuid4().hex
        flow_b = uuid.uuid4().hex

        a1 = Action(
            namespace="Concept/op", inputs={"val": "a"}, outputs={"ok": True},
            flow_token=flow_a,
        )
        a2 = Action(
            namespace="Concept/op", inputs={"val": "b"}, outputs={"ok": True},
            flow_token=flow_b,
        )

        store = await store_factory()
        history_a = await store.add_action(a1)
        history_b = await store.add_action(a2)

        combined = history_a + history_b

        pattern = [ActionPattern("Concept/op", inputs={"val": "a"}, outputs={})]

        result = Matcher.match_when(pattern, combined, flow_a)
        assert result is not None
        bindings, ids = result
        assert a1.id in ids

        result_b = Matcher.match_when(pattern, combined, flow_b)
        assert result_b is None


class TestFiringIdempotency:

    @pytest.mark.parametrize("store_factory", STORE_FACTORIES)
    @pytest.mark.asyncio
    async def test_record_sync_edge_returns_true_first_false_second(self, store_factory):
        store = await store_factory()
        action_id = uuid.uuid4().hex
        to_id = uuid.uuid4().hex

        first = await store.record_sync_edge(action_id, "MySyncRule", to_id)
        second = await store.record_sync_edge(action_id, "MySyncRule", to_id)

        assert first is True
        assert second is False

    @pytest.mark.parametrize("store_factory", STORE_FACTORIES)
    @pytest.mark.asyncio
    async def test_different_sync_names_fire_independently(self, store_factory):
        store = await store_factory()
        action_id = uuid.uuid4().hex

        r1 = await store.record_sync_edge(action_id, "SyncA", uuid.uuid4().hex)
        r2 = await store.record_sync_edge(action_id, "SyncB", uuid.uuid4().hex)

        assert r1 is True
        assert r2 is True

    @pytest.mark.parametrize("store_factory", STORE_FACTORIES)
    @pytest.mark.asyncio
    async def test_engine_fires_sync_exactly_once_end_to_end(self, store_factory):
        fired: list = []

        async def concept_a(inputs):
            return {"done": True}

        async def concept_b(inputs):
            fired.append("B")
            return {"done": True}

        async def terminal(inputs):
            return {"delivered": True}

        rules = [
            Sync("TriggerB")
            .when(ActionPattern("ConceptA/run", outputs={"done": True}))
            .then(ActionPattern("ConceptB/run", inputs={}))
            .build(),
            Sync("Respond")
            .when(ActionPattern("ConceptB/run", outputs={"done": True}))
            .then(ActionPattern("Web/respond", inputs={"status": 200}))
            .build(),
        ]

        store = await store_factory()
        bus = InMemoryBus()
        dispatcher = AppDispatcher(bus)
        dispatcher.register_action("ConceptA/run", concept_a)
        dispatcher.register_action("ConceptB/run", concept_b)
        dispatcher.register_action("Web/respond", terminal)
        gateway = FlowGateway(bus)

        engine = SyncEngine(bus, store, dispatcher, rules)
        await engine.start()
        await gateway.listen()

        root = Action(
            namespace="ConceptA/run",
            inputs={},
            outputs={"done": True},
            flow_token=uuid.uuid4().hex,
        )
        result = await gateway.ask(root, timeout=3.0)

        assert result["status"] == 200
        count = fired.count("B")
        assert count == 1, f"ConceptB must fire exactly once, fired {count} times"

    @pytest.mark.parametrize("store_factory", STORE_FACTORIES)
    @pytest.mark.asyncio
    async def test_idempotency_survives_simulated_restart(self, store_factory):
        store = await store_factory()
        action_id = uuid.uuid4().hex
        to_id = uuid.uuid4().hex

        r1 = await store.record_sync_edge(action_id, "ReplayRule", to_id)
        assert r1 is True

        r2 = await store.record_sync_edge(action_id, "ReplayRule", uuid.uuid4().hex)
        assert r2 is False


class TestProvenanceCompleteness:

    @pytest.mark.parametrize("store_factory", STORE_FACTORIES)
    @pytest.mark.asyncio
    async def test_root_action_has_no_provenance(self, store_factory):
        store = await store_factory()
        root = _root_action("Web/request", pet_id="pet_1")
        await store.add_action(root)
        history = await store.get_history(root.flow_token)
        assert history[0].caused_by_sync is None
        if hasattr(store, "close"):
            await store.close()

    @pytest.mark.parametrize("store_factory", STORE_FACTORIES)
    @pytest.mark.asyncio
    async def test_derived_action_carries_sync_name(self, store_factory):
        store = await store_factory()
        flow = uuid.uuid4().hex
        derived = Action(
            namespace="Concept/op",
            inputs={},
            outputs={"ok": True},
            flow_token=flow,
            caused_by_sync="MySync",
        )
        await store.add_action(derived)
        history = await store.get_history(flow)
        assert history[0].caused_by_sync == "MySync"

    @pytest.mark.parametrize("store_factory", STORE_FACTORIES)
    @pytest.mark.asyncio
    async def test_engine_sets_caused_by_sync_on_invocations(self, store_factory):
        seen_caused_by: list = []

        async def concept(inputs):
            return {"done": True}

        async def terminal(inputs):
            return {"delivered": True}

        rules = [
            Sync("FireConcept")
            .when(ActionPattern("Root/trigger", outputs={}))
            .then(ActionPattern("Concept/run", inputs={}))
            .build(),
            Sync("Respond")
            .when(ActionPattern("Concept/run", outputs={"done": True}))
            .then(ActionPattern("Web/respond", inputs={"status": 200}))
            .build(),
        ]

        store = await store_factory()
        bus = InMemoryBus()
        dispatcher = AppDispatcher(bus)
        dispatcher.register_action("Concept/run", concept)
        dispatcher.register_action("Web/respond", terminal)

        async def observer(action: Action):
            if action.caused_by_sync is not None:
                seen_caused_by.append((action.namespace, action.caused_by_sync))

        await bus.subscribe(observer)

        gateway = FlowGateway(bus)
        engine = SyncEngine(bus, store, dispatcher, rules)
        await engine.start()
        await gateway.listen()

        root = Action(
            namespace="Root/trigger",
            inputs={},
            outputs={"received": True},
            flow_token=uuid.uuid4().hex,
        )
        await gateway.ask(root, timeout=3.0)

        namespaces = [ns for ns, _ in seen_caused_by]
        assert "Concept/run" in namespaces
        assert "Web/respond" in namespaces
        for ns, caused_by in seen_caused_by:
            assert caused_by is not None


class TestCausalOrdering:

    @pytest.mark.parametrize("store_factory", STORE_FACTORIES)
    @pytest.mark.asyncio
    async def test_fanout_where_fires_once_per_binding(self, store_factory):
        deleted: list = []

        async def delete_item(inputs):
            deleted.append(inputs["item_id"])
            return {"deleted": True}

        async def terminal(inputs):
            return {"delivered": True}

        items = ["item_1", "item_2", "item_3"]

        def expand_items(bindings):
            return [{**bindings, "item_id": item_id} for item_id in items]

        rules = [
            Sync("CascadeDelete")
            .when(ActionPattern("Collection/delete", outputs={}))
            .where(expand_items)
            .then(ActionPattern("Item/delete", inputs={"item_id": Var("item_id")}))
            .build(),
            Sync("Respond")
            .when(ActionPattern(
                "Item/delete", inputs={"item_id": "item_3"},
                outputs={"deleted": True},
            ))
            .then(ActionPattern("Web/respond", inputs={"status": 200}))
            .build(),
        ]

        store = await store_factory()
        bus = InMemoryBus()
        dispatcher = AppDispatcher(bus)
        dispatcher.register_action("Item/delete", delete_item)
        dispatcher.register_action("Web/respond", terminal)
        gateway = FlowGateway(bus)
        engine = SyncEngine(bus, store, dispatcher, rules)
        await engine.start()
        await gateway.listen()

        root = Action(
            namespace="Collection/delete",
            inputs={},
            outputs={"received": True},
            flow_token=uuid.uuid4().hex,
        )
        await gateway.ask(root, timeout=3.0)

        assert sorted(deleted) == sorted(items), (
            f"Each item must be deleted exactly once. Got: {deleted}"
        )


class TestSQLitePersistence:

    @pytest.mark.asyncio
    async def test_actions_persist_across_reopen(self, tmp_path):
        db_path = str(tmp_path / "test.db")

        flow = uuid.uuid4().hex
        action = Action(
            namespace="Concept/op",
            inputs={"x": 42},
            outputs={"y": 84},
            flow_token=flow,
            caused_by_sync="SomeSync",
        )

        store1 = await SQLiteFlowStore.create(db_path)
        await store1.add_action(action)
        await store1.close()

        store2 = await SQLiteFlowStore.create(db_path)
        history = await store2.get_history(flow)
        await store2.close()

        assert len(history) == 1
        reloaded = history[0]
        assert reloaded.namespace == "Concept/op"
        assert reloaded.inputs == {"x": 42}
        assert reloaded.outputs == {"y": 84}
        assert reloaded.flow_token == flow
        assert reloaded.caused_by_sync == "SomeSync"

    @pytest.mark.asyncio
    async def test_sync_edges_survive_action_eviction(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        store = await SQLiteFlowStore.create(db_path)

        flow = uuid.uuid4().hex
        action = Action(namespace="X/op", inputs={}, outputs={}, flow_token=flow)
        await store.add_action(action)
        await store.record_sync_edge(action.id, "SomeSync", uuid.uuid4().hex)

        await store.evict_flow(flow)

        history = await store.get_history(flow)
        assert history == []

        edges = await store.get_sync_edges(from_action_id=action.id)
        assert len(edges) == 1
        assert edges[0]["sync_name"] == "SomeSync"

        r = await store.record_sync_edge(action.id, "SomeSync", uuid.uuid4().hex)
        assert r is False

        await store.close()

    @pytest.mark.asyncio
    async def test_introspection_get_all_flows(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        store = await SQLiteFlowStore.create(db_path)

        flows = [uuid.uuid4().hex for _ in range(3)]
        for flow in flows:
            a = Action(namespace="X/op", inputs={}, outputs={}, flow_token=flow)
            await store.add_action(a)

        all_flows = await store.get_all_flows()
        assert set(all_flows) == set(flows)
        await store.close()
