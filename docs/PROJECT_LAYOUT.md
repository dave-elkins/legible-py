# LegiblePy: Canonical Project Layout

This document specifies the standard directory structure for a LegiblePy
application and the rules that govern what belongs in each location.

It is the structural expression of the design rules in Meng & Jackson's
*"What You See Is What It Does"* (Onward! 2025, Section 7.2), translated
from abstract principles into concrete filesystem conventions.

The Pet Store application (`examples/petstore/`) is the reference implementation of
this layout. Every rule stated here is verifiable by running `conceptlint`.

---

## Directory Structure

```
<project>/
  concepts/          ← one file per concept; pure domain logic only
    <concept>.py

  syncs/             ← one file per feature area; sync rules only
    <feature>.py

  app.py             ← FastAPI wiring: triggers, dispatcher, lifespan
  cli.py             ← CLI entry point (CliTrigger)

  engine/            ← LegiblePy sync engine (framework code, not edited)
  linter/            ← conceptlint (framework code, not edited)
  trace/             ← trace reader (framework code, not edited)
  tests/             ← contract, trigger, trace, and linter test suites
```

The three layers — `concepts/`, `syncs/`, and `app.py` — map directly to
the paper's three structural layers: independent concept services,
synchronization rules, and the bootstrap entry point.

---

## Layer Rules

### `concepts/<concept>.py`

Each concept lives in its own file. A concept file contains:

- A state dataclass (optional; only needed when state shape is documented)
- One or more `async def <action>(inputs: dict) -> dict` functions
- Pure helper functions used only within this concept (rare)

**What must not appear in a concept file:**

| Prohibited | Reason | Linter rule |
|---|---|---|
| `import concepts.<other>` | Concepts must not depend on each other | R001 |
| `from concepts.<other> import ...` | Same | R001 |
| State annotation using another concept's type | Couples schema across concepts | R002 |
| `async def action(...):` with no return | Action invisible to sync engine | R003 |
| `import fastapi`, `import uvicorn` | Framework code does not belong in concepts | — |
| `Sync(...)`, `SyncRule(...)` | Sync rules belong in `syncs/` | — |

**What is expected in a concept file:**

```python
# concepts/inventory.py
import asyncio

async def check(inputs: dict) -> dict:
    """Check whether a pet is available for purchase."""
    pet_id = inputs.get("pet_id")
    if pet_id == "pet_1":
        return {"available": True, "price": 250.0}
    return {"available": False, "price": 0.0}
```

Concepts reference other concepts only through **uninterpreted atoms** —
opaque string identifiers (UUIDs) that carry no type information about
the entity they identify. A `pet_id` in the Inventory concept is a
string, not a `Pet` object from a hypothetical `concepts/pet.py`.

**Verify with:**
```
conceptlint concepts/*.py
```
Expected: zero violations.

---

### `syncs/<feature>.py`

Each sync file groups related sync rules by feature area. A sync file contains:

- `Sync(...).when(...).where(...).then(...).build()` rule definitions
- A `get_<feature>_rules() -> list[SyncRule]` function that returns them
- Pure where-clause helper functions (read-only, no side effects)

**What must not appear in a sync file:**

| Prohibited | Reason | Linter rule |
|---|---|---|
| `import concepts.<anything>` | Syncs reference concepts by namespace string, not by import | R001 |
| `async def action(...)` definitions | Actions live in `concepts/`, not `syncs/` | — |
| Side effects in `where` callables | `where` clauses must be pure reads | R005 |
| `import fastapi`, `from fastapi import ...` | Framework code does not belong in syncs | — |

**What is expected in a sync file:**

```python
# syncs/purchase.py
from engine import ActionPattern, Sync, Var

def get_purchase_rules():
    return [
        Sync("CheckInventory")
        .when(ActionPattern(
            "Web/purchase_request",
            inputs={"pet_id": Var("pet_id"), "customer_id": Var("cust_id")},
            outputs={},
        ))
        .then(ActionPattern("Inventory/check", inputs={"pet_id": Var("pet_id")}))
        .build(),

        # ... more rules
    ]
```

Note that concepts are referenced by their **namespace string**
(`"Inventory/check"`) not by import. This is the structural guarantee
that syncs do not couple to concept implementation details.

**Verify with:**
```
conceptlint syncs/*.py
```
Expected: zero violations.

---

### `app.py`

The application wiring layer. Contains:

- `InMemoryBus`, `AppDispatcher`, `FlowGateway`, `SyncEngine` construction
- `SQLiteFlowStore` initialisation (or `InMemoryFlowStore` for testing)
- `dispatcher.register_action(namespace, handler)` calls — this is where
  namespace strings are bound to concept functions
- Trigger construction (`HttpTrigger`, `AsyncLlmTrigger`)
- FastAPI `app` instance, `lifespan` context manager, route handlers
- Pydantic request/response models

**What must not appear in `app.py`:**

| Prohibited | Reason |
|---|---|
| `async def <action>(inputs: dict) -> dict` domain functions | These belong in `concepts/` |
| `Sync(...).when(...).then(...)` rule definitions | These belong in `syncs/` |
| Business logic inside route handlers | Route handlers should call triggers only |

**What a clean route handler looks like:**

```python
@app.post("/purchase")
async def purchase_pet(request: PurchaseRequest):
    try:
        return await purchase_trigger.fire(request.model_dump())
    except TriggerError as e:
        raise HTTPException(status_code=e.status_code, detail=e.result)
    except (RuntimeError, asyncio.TimeoutError) as e:
        raise HTTPException(status_code=500, detail=str(e))
```

The route handler knows nothing about concepts, sync rules, or flow tokens.
It hands a payload to a trigger and translates the result to HTTP.

`app.py` is not linted by `conceptlint` — it intentionally contains
infrastructure code that mixes async patterns, framework imports, and
lifecycle management. The clean separation enforced by the layout means
this mixing is contained to exactly one file.

---

### `cli.py`

The CLI entry point. Contains:

- A fresh `InMemoryBus`, `AppDispatcher`, `FlowGateway`, `SyncEngine` stack
  (separate from the FastAPI stack — CLI runs in its own event loop)
- `CliTrigger` construction with `engine_starters`
- `if __name__ == "__main__":` entry point

```python
# cli.py
import sys
from engine import (
    AppDispatcher, CliTrigger, FlowGateway, InMemoryBus,
    SQLiteFlowStore, SyncEngine,
)
from concepts.inventory import check as check_inventory
from concepts.order import create as create_order
from concepts.billing import charge as charge_billing
from syncs.purchase import get_purchase_rules


async def _boot(bus, dispatcher, gateway):
    store = await SQLiteFlowStore.create(":memory:")
    engine = SyncEngine(bus, store, dispatcher, get_purchase_rules())
    await engine.start()
    await gateway.listen()

# ... CliTrigger construction and trigger.run(...)
```

Note that `cli.py` *does* import from `concepts/` — this is the only
place outside `app.py` where concept functions are imported by name.
This is correct: `cli.py` is wiring, not a concept.

---

## The Three-Layer Dependency Rule

Dependencies flow in one direction only:

```
app.py / cli.py
    ↓ imports
concepts/<concept>.py    syncs/<feature>.py
    ↓ no imports between    ↓ no imports from concepts/
    (concepts are independent)
```

- `app.py` and `cli.py` import from both `concepts/` and `syncs/`
- `syncs/` imports from `engine/` only (for `Sync`, `ActionPattern`, `Var`)
- `concepts/` imports from stdlib and third-party libraries only

No file in `concepts/` imports from `syncs/` or vice versa.
No file in `syncs/` imports from `concepts/`.

---

## Linter Verification Matrix

Running `conceptlint` across the project verifies the layout rules
that are statically checkable:

| Location | Command | Expected result |
|---|---|---|
| Concept modules | `conceptlint concepts/*.py` | Zero violations |
| Sync modules | `conceptlint syncs/*.py` | Zero violations |
| Fixtures (clean) | `conceptlint tests/fixtures/clean_concept.py` | Zero violations |
| Fixtures (bad) | `conceptlint tests/fixtures/bad_concept.py` | All rules triggered |

`app.py` and `cli.py` are excluded from linting — they are wiring
layers that intentionally use infrastructure imports.

---

## What the Linter Cannot Check

Some design rules require human review or a concept registry that
does not yet exist statically:

- **R006 (deferred) — op-principle-spans-concepts:** A docstring that
  describes behaviour spanning multiple concepts. Requires knowing all
  concept names in the project.

- **Sync files referencing wrong namespaces:** If a sync rule uses
  `"Inventory/chekc"` (typo), `conceptlint` will not catch it. The
  engine will silently never match. A namespace registry (future work)
  would make this checkable statically.

- **Concept files with correct imports but wrong semantics:** A concept
  that calls an external HTTP API is not prohibited by any lint rule,
  but may violate the intent of concept independence depending on context.

---

## Example: Before and After

The Pet Store's `app.py` before Milestone 4.2 mixed all four concerns:

```
app.py (before)
  ├── async def check_inventory(...)     ← concept
  ├── async def create_order(...)        ← concept
  ├── async def charge_billing(...)      ← concept
  ├── async def mock_web_respond(...)    ← concept
  ├── def get_rules() -> list            ← syncs
  ├── bus = InMemoryBus()                ← wiring
  ├── purchase_trigger = HttpTrigger()   ← wiring
  ├── lifespan(...)                      ← wiring
  ├── @app.post("/purchase")             ← wiring
  └── def cli_purchase()                 ← CLI entry point
```

After Milestone 4.2:

```
concepts/
  inventory.py    ← check_inventory (renamed to check)
  order.py        ← create_order (renamed to create)
  billing.py      ← charge_billing (renamed to charge)
  web.py          ← mock_web_respond (renamed to respond)

syncs/
  purchase.py     ← get_purchase_rules() + HandleLlmRecommendation

app.py            ← wiring only: bus, dispatcher, triggers, routes
cli.py            ← CliTrigger entry point
```

`conceptlint concepts/*.py` → zero violations.
`conceptlint syncs/*.py` → zero violations.

---

*Document version: June 2026 — Milestone 4.1*
*Companion: ROADMAP.md, Milestone 4.2 (Pet Store Refactor)*
