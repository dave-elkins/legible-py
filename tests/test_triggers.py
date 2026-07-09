from __future__ import annotations

import asyncio
import json

import pytest

from legible.engine import (
    Action,
    ActionPattern,
    AppDispatcher,
    AsyncLlmTrigger,
    AsyncTrigger,
    CliTrigger,
    FlowGateway,
    HttpTrigger,
    InMemoryBus,
    InMemoryFlowStore,
    Sync,
    SyncEngine,
    Trigger,
    TriggerError,
    Var,
)


async def _make_engine(rules, extra_handlers=None):
    bus = InMemoryBus()
    store = InMemoryFlowStore()
    dispatcher = AppDispatcher(bus)
    gateway = FlowGateway(bus, terminal_namespace="Web/respond")

    async def _noop(inputs): return {"delivered": True}
    dispatcher.register_action("Web/respond", _noop)

    if extra_handlers:
        for ns, handler in extra_handlers.items():
            dispatcher.register_action(ns, handler)

    engine = SyncEngine(bus, store, dispatcher, rules)
    await engine.start()
    await gateway.listen()
    return bus, gateway, dispatcher


def _passthrough_rules(root_ns):
    return [
        Sync("Respond")
        .when(ActionPattern(root_ns, outputs={}))
        .then(ActionPattern("Web/respond", inputs={"status": 200, "ok": True}))
        .build()
    ]


class TestHttpTrigger:

    @pytest.mark.asyncio
    async def test_fire_returns_result_on_success(self):
        bus, gateway, _ = await _make_engine(_passthrough_rules("Web/req"))
        trigger = HttpTrigger(gateway=gateway, namespace="Web/req")

        result = await trigger.fire({"x": 1})
        assert result == {"status": 200, "ok": True}

    @pytest.mark.asyncio
    async def test_fire_raises_trigger_error_on_error_map_match(self):
        bus, gateway, _ = await _make_engine([
            Sync("NotFound")
            .when(ActionPattern("Web/req", outputs={}))
            .then(ActionPattern("Web/respond", inputs={"status": 404, "msg": "nope"}))
            .build()
        ])
        trigger = HttpTrigger(
            gateway=gateway,
            namespace="Web/req",
            error_map={404: lambda r: r.get("status") == 404},
        )

        with pytest.raises(TriggerError) as exc_info:
            await trigger.fire({})
        assert exc_info.value.status_code == 404
        assert exc_info.value.result["msg"] == "nope"

    @pytest.mark.asyncio
    async def test_fire_raises_runtime_error_on_concept_failure(self):
        async def failing_concept(inputs):
            raise ValueError("boom")

        bus, gateway, dispatcher = await _make_engine(
            rules=[
                Sync("Run")
                .when(ActionPattern("Web/req", outputs={}))
                .then(ActionPattern("Concept/fail", inputs={}))
                .build()
            ],
            extra_handlers={"Concept/fail": failing_concept},
        )
        trigger = HttpTrigger(gateway=gateway, namespace="Web/req")

        with pytest.raises(RuntimeError, match="boom"):
            await trigger.fire({}, timeout=2.0)

    @pytest.mark.asyncio
    async def test_fire_propagates_payload_as_inputs(self):
        received_inputs = {}

        async def capture(inputs):
            received_inputs.update(inputs)
            return {"done": True}

        bus, gateway, dispatcher = await _make_engine(
            rules=[
                Sync("Run")
                .when(ActionPattern(
                    "Web/req",
                    inputs={"pet_id": Var("pet_id")},
                    outputs={},
                ))
                .then(ActionPattern("Concept/capture", inputs={"pet_id": Var("pet_id")}))
                .build(),
                Sync("Respond")
                .when(ActionPattern("Concept/capture", outputs={"done": True}))
                .then(ActionPattern("Web/respond", inputs={"status": 200}))
                .build(),
            ],
            extra_handlers={"Concept/capture": capture},
        )
        trigger = HttpTrigger(gateway=gateway, namespace="Web/req")
        await trigger.fire({"pet_id": "pet_1", "customer_id": "alice"})

        assert received_inputs.get("pet_id") == "pet_1"

    @pytest.mark.asyncio
    async def test_satisfies_trigger_protocol(self):
        bus = InMemoryBus()
        gateway = FlowGateway(bus)
        trigger = HttpTrigger(gateway=gateway, namespace="Web/req")
        assert isinstance(trigger, Trigger)


class TestCliTrigger:

    def test_run_prints_json_result(self, capsys):
        bus = InMemoryBus()
        store = InMemoryFlowStore()
        dispatcher = AppDispatcher(bus)
        gateway = FlowGateway(bus, terminal_namespace="Web/respond")

        async def noop(inputs): return {"delivered": True}
        dispatcher.register_action("Web/respond", noop)

        rules = _passthrough_rules("Cli/req")
        engine = SyncEngine(bus, store, dispatcher, rules)

        async def boot():
            await engine.start()
            await gateway.listen()

        trigger = CliTrigger(
            bus=bus,
            gateway=gateway,
            namespace="Cli/req",
            engine_starters=[boot],
        )
        trigger.run({"x": 42})

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {"status": 200, "ok": True}

    def test_run_exits_nonzero_on_timeout(self, capsys):
        bus = InMemoryBus()
        store = InMemoryFlowStore()
        dispatcher = AppDispatcher(bus)
        gateway = FlowGateway(bus, terminal_namespace="Web/respond")

        engine = SyncEngine(bus, store, dispatcher, [])

        async def boot():
            await engine.start()
            await gateway.listen()

        trigger = CliTrigger(
            bus=bus,
            gateway=gateway,
            namespace="Cli/req",
            engine_starters=[boot],
        )

        with pytest.raises(SystemExit) as exc_info:
            trigger.run({}, timeout=0.1)
        assert exc_info.value.code == 1


class TestAsyncLlmTrigger:

    @pytest.mark.asyncio
    async def test_emit_returns_flow_token_immediately(self):
        bus = InMemoryBus()
        trigger = AsyncLlmTrigger(bus=bus, namespace="Llm/response")

        flow_token = await trigger.emit({"text": "hello"})
        assert isinstance(flow_token, str)
        assert len(flow_token) == 32

    @pytest.mark.asyncio
    async def test_emit_publishes_self_completing_root_action(self):
        bus = InMemoryBus()
        received = []

        async def observer(action: Action):
            received.append(action)

        await bus.subscribe(observer)

        trigger = AsyncLlmTrigger(bus=bus, namespace="Llm/response")
        flow_token = await trigger.emit({"conversation_id": "conv_1"})

        await asyncio.sleep(0.05)

        root_actions = [a for a in received if a.namespace == "Llm/response"]
        assert len(root_actions) == 1
        root = root_actions[0]
        assert root.flow_token == flow_token
        assert root.outputs == {"received": True}
        assert root.caused_by_sync is None
        assert root.inputs["conversation_id"] == "conv_1"

    @pytest.mark.asyncio
    async def test_on_complete_fires_when_flow_terminates(self):
        completed_flows = []

        bus, gateway, _ = await _make_engine([
            Sync("HandleLlm")
            .when(ActionPattern("Llm/response", outputs={}))
            .then(ActionPattern("Web/respond", inputs={"status": 200, "source": "llm"}))
            .build()
        ])

        trigger = AsyncLlmTrigger(
            bus=bus,
            namespace="Llm/response",
            terminal_namespace="Web/respond",
            on_complete=lambda flow_token, result: completed_flows.append(
                (flow_token, result)
            ),
        )

        flow_token = await trigger.emit({"conversation_id": "conv_99"})

        await asyncio.sleep(0.2)

        assert len(completed_flows) == 1
        token, result = completed_flows[0]
        assert token == flow_token
        assert result["status"] == 200
        assert result["source"] == "llm"

    @pytest.mark.asyncio
    async def test_on_complete_supports_async_callback(self):
        results = []

        async def async_callback(flow_token, result):
            await asyncio.sleep(0.01)
            results.append(result)

        bus, gateway, _ = await _make_engine(_passthrough_rules("Llm/response"))

        trigger = AsyncLlmTrigger(
            bus=bus,
            namespace="Llm/response",
            terminal_namespace="Web/respond",
            on_complete=async_callback,
        )
        await trigger.emit({})
        await asyncio.sleep(0.2)

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_multiple_emissions_produce_isolated_flows(self):
        completed = {}

        bus, gateway, _ = await _make_engine([
            Sync("HandleLlm")
            .when(ActionPattern(
                "Llm/response",
                inputs={"conv": Var("conv")},
                outputs={},
            ))
            .then(ActionPattern("Web/respond", inputs={"status": 200, "conv": Var("conv")}))
            .build()
        ])

        trigger = AsyncLlmTrigger(
            bus=bus,
            namespace="Llm/response",
            terminal_namespace="Web/respond",
            on_complete=lambda ft, r: completed.update({ft: r}),
        )

        token_a = await trigger.emit({"conv": "a"})
        token_b = await trigger.emit({"conv": "b"})
        await asyncio.sleep(0.3)

        assert token_a != token_b
        assert completed[token_a]["conv"] == "a"
        assert completed[token_b]["conv"] == "b"

    @pytest.mark.asyncio
    async def test_satisfies_async_trigger_protocol(self):
        bus = InMemoryBus()
        trigger = AsyncLlmTrigger(bus=bus, namespace="Llm/response")
        assert isinstance(trigger, AsyncTrigger)
