# Pure Function Concepts — Deterministic, Stateful Variant

Alternate implementation of the Pet Store concepts using **synchronous
pure functions with explicit state management**.

Compared to the async concepts in `examples/petstore/concepts/`, these
functions are:

- **Deterministic** — same inputs always produce the same outputs
  (counter-based IDs instead of UUIDs)
- **State-managing** — `(state, inputs) → (new_state, outputs)` signature
- **Sync** — no `async`/`await`, no I/O, testable without an event loop
- **Immutable** — return new state objects instead of mutating in place

## Concept Files

| File | Type | Actions |
|---|---|---|
| `inventory.py` | `InventoryState`, `Pet` | `check(state, inputs)` |
| `order.py` | `OrderState`, `Order` | `create(state, inputs)` |
| `billing.py` | `BillingState`, `Charge` | `charge(state, inputs)` |
| `web.py` | `WebState` (empty) | `respond(state, inputs)` |

## Usage

These concepts are designed to be used with `PureFunctionDispatcher`
instead of `AppDispatcher`:

```python
from legible.engine import (
    PureFunctionDispatcher, InMemoryStateStore,
    InMemoryBus, InMemoryFlowStore, SyncEngine, FlowGateway, HttpTrigger,
)
from examples.concepts_pure.inventory import InventoryState, check as inv_check
from examples.concepts_pure.order import OrderState, create as ord_create
from examples.concepts_pure.billing import BillingState, charge as bill_charge
from examples.concepts_pure.web import WebState, respond as web_respond
from examples.petstore.syncs.purchase import get_purchase_rules

bus = InMemoryBus()
dispatcher = PureFunctionDispatcher(bus)

dispatcher.register_concept("Inventory/check", inv_check,
                            InMemoryStateStore(InventoryState()))
dispatcher.register_concept("Order/create", ord_create,
                            InMemoryStateStore(OrderState()))
dispatcher.register_concept("Billing/charge", bill_charge,
                            InMemoryStateStore(BillingState()))
dispatcher.register_concept("Web/respond", web_respond,
                            InMemoryStateStore(WebState()))

store = InMemoryFlowStore()
gateway = FlowGateway(bus, terminal_namespace="Web/respond")
engine = SyncEngine(bus, store, dispatcher, get_purchase_rules())

# Run it (in an async context)
# await engine.start()
# await gateway.listen()
# result = await HttpTrigger(gateway, "Web/purchase_request")
#     .fire({"pet_id": "pet_1", "customer_id": "alice"})
```

## Testing

```bash
# From repo root
python -m pytest tests/test_pure_storage.py --asyncio-mode=auto -v
```

## Key Differences from Async Concepts

| Aspect | Async (`petstore/concepts/`) | Pure (`concepts_pure/`) |
|---|---|---|
| Signature | `async fn(inputs) → dict` | `fn(state, inputs) → (state, outputs)` |
| IDs | `uuid4` (non-deterministic) | Incrementing counter (deterministic) |
| Error handling | Raise exceptions | Return `{"error": ...}` in outputs |
| Dispatcher | `AppDispatcher` | `PureFunctionDispatcher` |
| State | Stateless (no state layer) | Explicit via `InMemoryStateStore` |
| Imports | `asyncio`, `uuid` | `dataclasses`, `typing` only |
