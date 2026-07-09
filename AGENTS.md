# AGENTS.md

Operational guide for AI coding agents (Claude Code, OpenCode, and similar)
working in the LegiblePy codebase.

Read this file before generating any code. Read `docs/concept-design.md` for
vocabulary and design rules.

---

## What this project is

LegiblePy is a Python implementation of the WYSIWID (What You See Is What
It Does) sync engine described in Meng & Jackson's *"What You See Is What
It Does"* (Onward! 2025). It provides a runtime for **Concept Design** —
an approach to structuring software so that every observable behaviour maps
directly to a named, independent unit of code.

The project has two purposes:
1. A working open-source sync engine
2. A companion book documenting the build process

The **Pet Store** (`examples/petstore/`) is the running demonstration case throughout
both the code and the writing.

---

## Repository layout

```
engine/          sync engine — do not edit unless extending the engine itself
  models.py      Action, ActionPattern, Var, SyncRule, Sync, Matcher
  store.py       FlowStore protocol + InMemoryFlowStore
  store_sqlite.py SQLiteFlowStore (durable backend)
  bus.py         InMemoryBus (fanout pub/sub)
  dispatcher.py  AppDispatcher + FlowGateway
  engine.py      SyncEngine
  triggers.py    HttpTrigger, CliTrigger, AsyncLlmTrigger

linter/          conceptlint static analyser — do not edit
  rules.py       R001–R005 AST rules
  cli.py         CLI entry point

trace/           flow visualiser — do not edit
  model.py       FlowTrace, TraceNode, build_trace()
  render.py      render_tree(), render_json()
  cli.py         CLI entry point

examples/petstore/        reference application — primary editing target
  concepts/      one file per concept; pure domain logic only
  syncs/         one file per feature area; sync rules only
  app.py         FastAPI wiring (triggers, dispatcher, lifespan, routes)
  cli.py         CliTrigger entry point

tests/           test suites — extend when adding features
  test_contract.py   engine contract (23 tests)
  test_triggers.py   trigger abstraction (13 tests)
  test_trace.py      trace reader (23 tests)
  test_linter.py     conceptlint (49 tests)
  test_petstore.py   Pet Store integration (20 tests)
  fixtures/          clean_concept.py, bad_concept.py
```

---

## The three-layer rule

Every piece of application code belongs in exactly one layer:

```
concepts/<name>.py   — what things DO (domain logic, no framework)
syncs/<feature>.py   — how things are COORDINATED (sync rules, no concepts)
app.py / cli.py      — how things are WIRED (triggers, dispatcher, routes)
```

Dependencies flow downward only:

```
app.py / cli.py
    ↓ imports concepts + syncs
concepts/   (no imports from syncs/ or other concepts/)
syncs/      (no imports from concepts/; references by namespace string)
```

Violating this rule is not a style issue — it breaks the engine's contract
invariants. See `docs/concept-design.md` for the reasoning.

---

## Before you commit generated code

Run the linter on every concept and sync file you generate or modify:

```bash
python -m linter.cli examples/petstore/concepts/*.py
python -m linter.cli examples/petstore/syncs/*.py
```

Both commands must exit 0 with "No violations found" before the code is
considered correct. Do not submit code that fails these checks.

Run the full test suite:

```bash
python -m pytest tests/ --asyncio-mode=auto -q
```

All 128 tests must pass. If you add a new concept or sync rule, add
corresponding tests in `tests/test_petstore.py`.

---

## How to add a new concept

1. Create `examples/petstore/concepts/<name>.py`.
2. Write one or more `async def <action>(inputs: dict) -> dict` functions.
3. Each function must return a dict — never `None`, never void.
4. Use only stdlib and approved third-party imports. No `fastapi`, no
   `engine`, no imports from other concept files.
5. Run `python -m linter.cli examples/petstore/concepts/<name>.py` — must be zero
   violations.
6. Add the concept to `examples/petstore/app.py` via
   `dispatcher.register_action("Concept/action", handler)`.
7. Write unit tests in `tests/test_petstore.py` calling the function
   directly — no engine required.

**Example:**

```python
# examples/petstore/concepts/notification.py
"""
Notification concept — sends messages to users.

Namespace: Notification
Actions:   Notification/send
"""
import asyncio

async def send(inputs: dict) -> dict:
    """Send a notification to a user.

    Inputs:  user_id (str), message (str)
    Outputs: sent (bool), notification_id (str)
    """
    await asyncio.sleep(0.01)
    return {"sent": True, "notification_id": f"notif_{inputs['user_id'][:4]}"}
```

---

## How to add a new sync rule

1. Open the appropriate `examples/petstore/syncs/<feature>.py` file, or create a
   new one if the feature area is new.
2. Add a `Sync("RuleName").when(...).then(...).build()` call.
3. Reference concepts by **namespace string only** — never import concept
   modules in a sync file.
4. If the rule needs a `where` clause, write a plain (non-async) function
   that takes `bindings: dict` and returns `list[dict]`. No side effects.
5. Run `python -m linter.cli examples/petstore/syncs/<feature>.py` — must be zero
   violations.
6. Register the rule by adding it to the list returned by
   `get_<feature>_rules()` — it is automatically picked up by `app.py`.

**Example:**

```python
# In examples/petstore/syncs/purchase.py — adding a notification on purchase
Sync("NotifyOnPurchase")
.when(ActionPattern(
    "Billing/charge",
    outputs={"status": "paid", "receipt_id": Var("rcpt")},
))
.then(ActionPattern(
    "Notification/send",
    inputs={"user_id": Var("cust_id"), "message": "Your pet is on its way!"},
))
.build(),
```

---

## How to read a flow trace

After running the server and making a request, inspect what happened:

```bash
# List all recorded flows
python trace/cli.py --list --db legible.db

# Show the causal tree for a flow (use prefix from --list output)
python trace/cli.py <flow_prefix> --db legible.db

# Machine-readable output for parsing
python trace/cli.py <flow_prefix> --db legible.db --format json
```

If a sync rule is not firing as expected, the trace tree shows exactly which
actions completed and which sync names were attributed to them. A rule that
never appears in the trace tree either never matched or was never registered.

---

## How to run the server

```bash
cd examples/petstore
uvicorn app:app --reload

# Test the three purchase paths
curl -X POST http://localhost:8000/purchase \
     -H 'Content-Type: application/json' \
     -d '{"pet_id":"pet_1","customer_id":"alice"}'   # 200 success

curl -X POST http://localhost:8000/purchase \
     -H 'Content-Type: application/json' \
     -d '{"pet_id":"pet_2","customer_id":"bob"}'     # 404 out of stock

curl -X POST http://localhost:8000/purchase \
     -H 'Content-Type: application/json' \
     -d '{"pet_id":"pet_3","customer_id":"charlie"}' # 500 infra error

# LLM trigger (fire-and-observe)
curl -X POST http://localhost:8000/llm/response \
     -H 'Content-Type: application/json' \
     -d '{"conversation_id":"conv_1","text":"recommendation"}'
```

---

## What NOT to do

- Do not add `import concepts.<anything>` to a sync file.
- Do not add `import syncs.<anything>` to a concept file.
- Do not define concept functions in `app.py`.
- Do not define sync rules in `app.py`.
- Do not write `async def where_clause(...)` — where clauses are plain
  synchronous functions.
- Do not call `await` inside a where clause, even in a nested function.
- Do not mutate external state in a where clause (no `.append()`,
  no dict assignment to non-local variables).
- Do not write an action that returns nothing or returns `None`.
- Do not add business logic to FastAPI route handlers — route handlers
  call triggers only.

The linter catches most of these. Run it.

---

## Key files to read before making changes

| Task | Read first |
|---|---|
| Adding a concept | `docs/concept-design.md` §Concepts, `docs/PROJECT_LAYOUT.md` §concepts/ |
| Adding a sync rule | `docs/concept-design.md` §Synchronizations, `docs/PROJECT_LAYOUT.md` §syncs/ |
| Changing the engine | `engine/engine.py` docstring, `docs/ROADMAP.md` |
| Debugging a flow | `trace/model.py` docstring, `trace/cli.py --help` |
| Understanding a lint error | `linter/rules.py` — each rule has a full docstring |

---

*Last updated: June 2026 — Milestone 4.3*
