# LegiblePy: Project Roadmap

A phased plan for building a Python WYSIWID sync engine and developer tooling,
addressing the open gaps identified in Meng & Jackson's "What You See Is What It Does" (Onward! 2025).

## Dependency Structure

- **Phase 1 (engine + contract)** — the foundation everything else needs
- **Phase 2 (extensions)** — engine variants built on the stable baseline
- **Phase 3 (tooling)** — observability and quality tools
- **Phase 4 (structure)** — proper project layout, discovered by running the tooling

-----

## Phase 1 — Engine Foundation ✅ COMPLETE

### Milestone 1.1 — Engine Contract Specification ✅

Five invariants, documented in module docstrings and verified by `tests/test_contract.py`:

| Invariant | Statement |
|---|---|
| **Flow isolation** | All actions triggered within a sync share the same `flow_token`. `Matcher` filters history to a single flow before pattern matching. |
| **Firing idempotency** | A sync fires at most once per `(matched_action_set, sync_name)` pair. Survives process restarts. |
| **No cross-concept calls** | Concepts are plain `async (inputs: dict) -> dict` functions. No concept imports another. |
| **Provenance completeness** | Every non-root `Action` carries `caused_by_sync`. Root triggers carry `None`. |
| **Causal ordering** | Completions processed in causal order via per-subscriber asyncio queues. |

### Milestone 1.2 — Core Data Structures ✅

`engine/` package. Original ROADMAP specified four files; actual split:

| ROADMAP spec | Actual file | Notes |
|---|---|---|
| `action_record.py` | `engine/models.py` | Also contains `ActionPattern`, `Var`, `SyncRule`, `Sync`, `Matcher` |
| `flow_graph.py` | `engine/store.py` | `FlowStore` protocol + `InMemoryFlowStore` |
| `sync_rule.py` | merged into `models.py` | |
| `engine.py` | `engine/engine.py` | `SyncEngine` only |
| *(not in ROADMAP)* | `engine/bus.py` | `InMemoryBus` — fanout pub/sub with per-subscriber queues |
| *(not in ROADMAP)* | `engine/dispatcher.py` | `AppDispatcher` + `FlowGateway` |

**Key design decision:** The ROADMAP specified `(action_record_id, sync_name)` as the
deduplication key. This was wrong — the engine re-evaluates all rules on every new
completion. The correct key uses the *matched* action ids:

```python
match_key = "__".join(sorted(matched_ids))
await store.record_sync_edge(match_key, rule.name, action.id)
```

### Milestone 1.3 — In-Memory Engine + Contract Tests ✅

23 tests, all passing.

### Milestone 1.4 — SQLite Backend ✅

`engine/store_sqlite.py` — `SQLiteFlowStore` with archival support.

Schema:
```sql
action_records           -- live history for in-flight flows
completed_action_records -- archived history for completed flows (retain_history=True)
sync_edges               -- durable idempotency record (PRIMARY KEY enforces no re-fire)
```

Three first-principles gaps from the paper closed:

| Principle | Before | After |
|---|---|---|
| 5 — Firing idempotency | Lost on restart | `INSERT OR IGNORE` on PK, restart-safe |
| 6 — Actions fully reified | Evicted on flow close | Archived in `completed_action_records` |
| 10 — Traces as natural byproduct | Gone after completion | Queryable via `get_any_history()` |

-----

## Phase 2 — Engine Extensions ✅ COMPLETE

### Milestone 2.1 — Generalized Trigger Abstraction ✅

*Addresses: paper Section 6.7 — the `Web` bootstrap concept is hardcoded to HTTP.*

`engine/triggers.py` — three concrete implementations behind two protocols.

**Design decision — two protocols, not one:**

| Protocol | Method | Implementations |
|---|---|---|
| `Trigger` | `async fire(payload) -> dict` | `HttpTrigger`, `CliTrigger` |
| `AsyncTrigger` | `async emit(payload) -> str` (flow_token) | `AsyncLlmTrigger` |

**Key architectural insight:** An LLM response arriving out-of-band is a new causal
root — not a downstream sync effect. Treating it as a root trigger keeps the causal
graph acyclic and provenance clean.

13 tests. **Running total: 36 tests, all passing.**

### Milestone 2.2 — Pure Function Storage Variant ✅ COMPLETE

*Addresses: paper Section 9 — "successfully prototyped" but never published.*

`engine/state_store.py`, `engine/pure_dispatcher.py`,
`examples/concepts_pure/` — 26 tests.

**What was built:**

`ConceptStateStore` protocol with two implementations:

| Implementation | Backing | Use case |
|---|---|---|
| `InMemoryStateStore` | Deep-copied Python value | Tests, in-process applications |
| `SqliteStateStore` | JSON in SQLite, one row per concept | Durable, restart-safe |

`PureFunctionDispatcher` — a drop-in replacement for `AppDispatcher` that handles
the state lifecycle per dispatch: `get()` → call handler → `set()` → publish completion.
Guards against async handlers (raises `TypeError` with an explanatory message).

Pure concept variants in `examples/concepts_pure/`:

```
examples/concepts_pure/
  inventory.py   InventoryState + check(state, inputs) -> (state, dict)
  order.py       OrderState    + create(state, inputs) -> (state, dict)
  billing.py     BillingState  + charge(state, inputs) -> (state, dict)
  web.py         WebState      + respond(state, inputs) -> (state, dict)
```

**The central payoff — concepts testable as pure functions:**

```python
# No engine. No bus. No async. No fixtures. Just a function call.
state = InventoryState()
new_state, outputs = check(state, {"pet_id": "pet_1"})
assert outputs == {"available": True, "price": 250.0}
assert new_state is state   # read-only: state unchanged
```

**Determinism as a first-class property:**

The pure variants replace `uuid4()` with integer counters, making outputs
fully deterministic: `result["receipt"] == "rcpt_0001"` asserts exactly.
This is impossible with the async variants.

**Design decision — `ConceptStateStore` vs "Store as concept":**

The paper's Section 9 prototype routes state persistence through a sync rule —
`Store/save` fires as a domain event after every action. This implementation
keeps the store as a dispatcher concern rather than a concept. The paper's
version is more architecturally pure; this version is easier to test and
reason about. Both are documented in the code; Chapter 12 explains the trade-off.

**`PureFunctionDispatcher` and `AppDispatcher` coexist:**
The `SyncEngine`, `FlowStore`, `FlowGateway`, triggers, and all existing tests
are entirely unchanged. Pure concepts are a drop-in at the dispatcher layer only.

26 new tests. **Running total: 154 tests, all passing.**

-----

## Phase 3 — Developer Tooling ✅ COMPLETE

### Milestone 3.1 — Trace Reader / Flow Visualiser ✅

*Addresses: paper Section 7.3 — sync granularity makes it hard to understand a full flow.*
*Closes: paper Section 7.4 debugging workflow — provenance-driven diagnosis.*

`trace/model.py`, `trace/render.py`, `trace/cli.py` — 23 tests.

`render_tree()` output:
```
Flow 91754bb9  │  5 action(s)  │  depth 5
└──●  Web/purchase_request  →  received=True
        ↳ [CheckInventory]
    └──●  Inventory/check  →  available=True  price=250.0
            ↳ [PlaceOrder]
        └──●  Order/create  →  order_id=ord_abc  status=pending
                ↳ [BillCustomer]
            └──●  Billing/charge  →  status=paid  receipt_id=rcpt_xyz
                    ↳ [SendReceipt]
                └──●  Web/respond  →  delivered=True
```

`render_json()` produces a serialisable `FlowTrace.to_dict()` — foundation for
the React DAG artifact in the book's provenance chapter.

CLI supports prefix matching, `--format json`, `--list` to enumerate all flows.

**Running total: 59 tests, all passing.**

### Milestone 3.2 — Concept Linter ✅

*Addresses: paper Section 7.3 — LLMs generate OO-contaminated concepts.*
*Closes: Principle 3 partial (where-clause enforcement) from the first-principles assessment.*

`linter/rules.py`, `linter/cli.py` — 49 tests.

Five rules (pure Python `ast`, no dependencies):

| Rule | ID | Level | What it detects |
|---|---|---|---|
| `no-cross-concept-import` | R001 | error | `import` of another concept module |
| `no-named-foreign-reference` | R002 | error | State annotation using a foreign concept type |
| `action-returns-void` | R003 | error | Async action with no return |
| `getter-smell` | R004 | warning | Single-key return, no mutation |
| `where-has-side-effects` | R005 | error | `where` callable with mutation or nested await |

**Running total: 108 tests, all passing.**

-----

## Phase 4 — Project Structure ✅ COMPLETE

*Discovered by: running `conceptlint` on `app.py` — false positives were the correct
signal that concept functions and infrastructure were mixed in a single file.*

### Milestone 4.1 — Canonical Project Layout ✅

`PROJECT_LAYOUT.md` — three-layer specification with linter verification matrix.

### Milestone 4.2 — Pet Store Refactor ✅

`examples/petstore/` — reference implementation of the canonical layout.
`conceptlint examples/petstore/concepts/*.py` and `conceptlint examples/petstore/syncs/*.py` both exit 0.
20 new tests including `TestConceptsInIsolation` and `TestLinterAcceptanceCriteria`.

**Running total: 128 tests, all passing.**

### Milestone 4.3 — ../AGENTS.md and concept-design.md ✅

Two documents completing the AI-assisted development pipeline:

```
Prompt → LLM generates concept → conceptlint verifies → engine runs → trace reader diagnoses
```

`../AGENTS.md` — operational (task checklists, commands, prohibitions).
`concept-design.md` — educational (vocabulary, design rules, common mistakes).

-----

## Summary

```
Phase 1 — Engine Foundation                            ✅ COMPLETE
  1.1  Engine contract (5 invariants)                  ✅
  1.2  Core data structures (engine/ package)          ✅
  1.3  In-memory engine + 23 contract tests            ✅
  1.4  SQLite backend + archival (contract parity)     ✅

Phase 2 — Extensions                                   ✅ COMPLETE
  2.1  Generalized Trigger abstraction                 ✅
       HttpTrigger, CliTrigger, AsyncLlmTrigger
  2.2  Pure function storage variant                   ✅
       ConceptStateStore, PureFunctionDispatcher,
        examples/concepts_pure/, 26 tests

Phase 3 — Tooling                                      ✅ COMPLETE
  3.1  Trace reader / flow visualiser                  ✅
  3.2  Concept linter (5 rules, 49 tests)              ✅

Phase 4 — Project Structure                            ✅ COMPLETE
  4.1  Canonical layout (PROJECT_LAYOUT.md)            ✅
  4.2  Pet Store refactor (128 tests passing)          ✅
   4.3  ../AGENTS.md + concept-design.md                   ✅

Total: 154 tests, all passing.
All planned milestones complete.
```

## What's next

All planned milestones are complete. The natural next areas are:

**Book writing.** Every chapter in the book alignment table now has a working
artifact behind it. The most book-ready artifacts, in order:

1. Engine contract (Chapter 5) — the five invariants and their test cases are the
   cleanest technical writing in the codebase
2. The idempotency key decision (Chapter 7) — a self-contained story of a wrong
   decision, its discovery, and the correct fix
3. Pure function storage (Chapter 12) — the unpublished contribution; the
   `ConceptStateStore` vs "Store as concept" trade-off is the chapter's spine
4. What the linter tells you (Chapter 15) — the false-positive-as-signal story
   is concrete, short, and demonstrates the architecture's self-consistency

**React DAG artifact.** An interactive flow visualiser built on `render_json()`
output. The data structure is already defined; this is a frontend-only milestone.

**Namespace registry.** Static check for namespace typos in sync rules — closes
the gap documented in `PROJECT_LAYOUT.md` under "What the Linter Cannot Check."
Prerequisite for R006 (op-principle-spans-concepts).

**R006 — op-principle-spans-concepts.** The deferred linter rule. Implementable
once a namespace registry provides the list of known concept names.

## Book Alignment

| Milestone | Book chapter |
|---|---|
| 1.1 contract invariants | "What the Engine Must Guarantee" |
| 1.2 idempotency key design | "A Design Decision Worth Naming" |
| 1.4 SQLite + three-principle gap closure | "Three Principles, One Migration" |
| 2.1 Trigger vs AsyncTrigger split | "Two Kinds of Entry Point" |
| 2.1 AsyncLlmTrigger causal root insight | "LLM Responses Are Root Actions" |
| 2.2 pure functions + determinism | "Pure Function Storage (the Unpublished Contribution)" |
| 2.2 ConceptStateStore vs Store-as-concept | "Pure Function Storage (the Unpublished Contribution)" |
| 3.1 trace reader + legibility metrics | "Reading the Causal Record" |
| 3.2 concept linter — rules and rationale | "How to Keep Concepts Clean" |
| 3.2 linter on app.py — false positives as signal | "What the Linter Tells You" |
| 4.1 canonical layout | "Where Things Live" |
| 4.2 Pet Store before/after | "The Refactor the Linter Demanded" |
| 4.2 concepts testable in isolation | "What Clean Separation Enables" |
| 4.3 ../AGENTS.md + concept-design.md | "Orienting an AI Coding Agent" |

-----

*Updated: June 2026 — all planned milestones complete; 154 tests passing*
