# LegiblePy

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](pyproject.toml)
![Tests](https://img.shields.io/badge/tests-146%20passing-brightgreen)

A Python implementation of the **WYSIWID** (What You See Is What It Does)
sync engine for **Concept Design**, based on Meng & Jackson's
[*"What You See Is What It Does"*](https://2025.splashcon.org/details/splash-2025-onward/9/What-You-See-Is-What-It-Does)
(Onward! 2025).

Create software where every observable behaviour maps directly to a named,
independent unit of code — coordinated through declarative sync rules
instead of tangled call chains.

---

## Installation

```bash
pip install legible-py

# With web/server support (FastAPI + uvicorn):
pip install "legible-py[web]"
```

### From source

```bash
git clone https://github.com/dave-elkins/legible-py.git
cd legible-py
pip install -e ".[dev]"
```

---

## Quick Start

### Engine — compose independent concepts with sync rules

```python
from legible.engine import Sync, ActionPattern, Var, AppDispatcher, FlowGateway, InMemoryBus, SyncEngine

# 1. Write concepts — plain async functions returning dict
async def check(inputs: dict) -> dict:
    pet_id = inputs.get("pet_id")
    if pet_id == "pet_1":
        return {"available": True, "price": 250.0}
    return {"available": False, "price": 0.0}

async def respond(inputs: dict) -> dict:
    return {"delivered": True, "status": inputs["status"]}

# 2. Define sync rules — declarative when/where/then
rules = [
    Sync("CheckInventory")
    .when(ActionPattern("Web/request", outputs={}))
    .then(ActionPattern("Inventory/check", inputs={"pet_id": Var("pet_id")}))
    .build(),
    Sync("Respond")
    .when(ActionPattern("Inventory/check", outputs={"available": True}))
    .then(ActionPattern("Web/respond", inputs={"status": 200}))
    .build(),
]

# 3. Wire and run
bus = InMemoryBus()
dispatcher = AppDispatcher(bus)
gateway = FlowGateway(bus, terminal_namespace="Web/respond")
engine = SyncEngine(bus, store, dispatcher, rules)

dispatcher.register_action("Inventory/check", check)
dispatcher.register_action("Web/respond", respond)

await engine.start()
await gateway.listen()

result = await gateway.ask(
    Action(namespace="Web/request", inputs={"pet_id": "pet_1"})
)
# → {"delivered": True, "status": 200}
```

### Pure function variant — no async, no engine, no fixtures

```python
from legible.engine import PureFunctionDispatcher, InMemoryStateStore

state = InventoryState()
dispatcher = PureFunctionDispatcher(bus)
dispatcher.register_concept(
    "Inventory/check", pure_check, InMemoryStateStore(state)
)
```

---

## CLI

```bash
# Lint concept and sync files
lgbl lint concepts/*.py syncs/*.py

# Inspect a flow trace
lgbl trace <flow_token> --db legible.db

# List all recorded flows
lgbl trace --list --db legible.db
```

---

## API Overview

| Module | Entry Points | Purpose |
|---|---|---|
| `legible.engine` | `Sync`, `ActionPattern`, `Var`, `AppDispatcher`, `SyncEngine` | Sync engine core |
| `legible.engine` | `FlowGateway`, `HttpTrigger`, `CliTrigger`, `AsyncLlmTrigger` | Entry points & flows |
| `legible.engine` | `PureFunctionDispatcher`, `ConceptStateStore`, `InMemoryStateStore`, `SqliteStateStore` | Pure function variant |
| `legible.engine` | `InMemoryFlowStore`, `SQLiteFlowStore` | Storage backends |
| `legible.linter` | `lint_file`, `lint_source`, `LinterConfig` | Static analysis (5 rules) |
| `legible.trace` | `build_trace`, `render_tree`, `render_json` | Flow visualisation |

---

## Documentation

- **[AGENTS.md](AGENTS.md)** — operational guide (commands, workflows, file layout)
- **[docs/concept-design.md](docs/concept-design.md)** — vocabulary, first-principles, design rules
- **[docs/PROJECT_LAYOUT.md](docs/PROJECT_LAYOUT.md)** — canonical directory structure
- **[docs/ROADMAP.md](docs/ROADMAP.md)** — development history and future directions
- **[docs/BOOK_OUTLINE.md](docs/BOOK_OUTLINE.md)** — companion book outline

---

## Examples

### Pet Store (async concepts)

Full FastAPI application demonstrating the standard async engine with
`AppDispatcher`, `HttpTrigger`, and six purchase sync rules.

```bash
cd examples/petstore
pip install "legible-py[web]"
uvicorn app:app --reload

curl -X POST http://localhost:8000/purchase \
  -H 'Content-Type: application/json' \
  -d '{"pet_id":"pet_1","customer_id":"alice"}'
```

See [examples/petstore/README.md](examples/petstore/README.md).

### Pure Function Concepts

Deterministic, stateful variant using synchronous functions with
`PureFunctionDispatcher`. Same sync rules, no async, no I/O.

```bash
python -m pytest tests/test_pure_storage.py --asyncio-mode=auto -v
```

See [examples/concepts_pure/README.md](examples/concepts_pure/README.md).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, workflow, and code
guidelines. All contributions are welcome — please open an issue first
for significant changes.

---

## License

MIT — see [LICENSE.md](LICENSE.md).
