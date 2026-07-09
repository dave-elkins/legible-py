# Concept Design: Vocabulary Reference

A working reference for AI coding agents generating or modifying code in
a LegiblePy project. Covers vocabulary, design rules, common mistakes,
and how the linter catches them.

For operational instructions (commands, file locations, how to add things),
see `../AGENTS.md`.

---

## Core vocabulary

### Concept

A **concept** is an independent unit of functionality with a single,
well-defined purpose. It manages its own state and exposes a set of
actions. It has no knowledge of other concepts.

In LegiblePy, a concept is a Python module (`concepts/<name>.py`)
containing one or more `async def <action>(inputs: dict) -> dict`
functions. Nothing more.

```python
# concepts/inventory.py — the Inventory concept
async def check(inputs: dict) -> dict:
    pet_id = inputs.get("pet_id")
    if pet_id == "pet_1":
        return {"available": True, "price": 250.0}
    return {"available": False, "price": 0.0}
```

The concept's **namespace** is `Inventory`. Its **action** is `check`.
Together they form the action's full name: `Inventory/check`.

**Concepts are independent by definition.** The Inventory concept has no
idea what an Order is. The Order concept has no idea what Billing is.
The sync layer coordinates them.

---

### Action

An **action** is a named operation that a concept can perform. In
LegiblePy, every action is an `async def` that takes `inputs: dict` and
returns `dict`.

Rules for actions:
- Must return a dict. An action that returns nothing is invisible to the
  sync engine — it can never be matched in a `when` clause.
- The return dict is called the **outputs**. Any key can appear; the names
  matter for pattern matching in sync rules.
- Raise an exception for error paths — the engine catches exceptions and
  stores `{"error": str(e)}` as the outputs, which sync rules can match.

```python
# Good — returns a dict
async def create(inputs: dict) -> dict:
    return {"order_id": "ord_abc", "status": "pending"}

# Bad — returns None (R003 violation)
async def notify(inputs: dict):
    send_email(inputs["address"])
```

---

### Synchronization (sync rule)

A **sync rule** describes how the actions of independent concepts are
coordinated. It has the form:

> *When* these actions complete *where* these conditions hold,
> *then* invoke these other actions.

In LegiblePy, sync rules are built with the fluent DSL:

```python
Sync("RuleName")
.when(ActionPattern(...))       # what completions to match
.where(condition_fn)            # optional: filter or expand bindings
.then(ActionPattern(...))       # what to invoke
.build()
```

Sync rules live in `syncs/<feature>.py`. They reference concepts by
**namespace string**, never by import.

---

### ActionPattern

An `ActionPattern` matches an action record in the flow history.

```python
ActionPattern(
    "Inventory/check",               # namespace: Concept/action
    inputs={"pet_id": Var("pid")},   # match inputs; Var binds a variable
    outputs={"available": True,      # match outputs; only for completions
             "price": Var("price")},
)
```

- `inputs={}` matches any completion regardless of inputs
- `outputs={}` matches any completion regardless of outputs
- `outputs=None` (default) matches both invocations and completions
- A dict with specific keys matches only completions where those keys are
  present with those values (or binds them to Var names)

---

### Var

`Var("name")` is a binding variable in a pattern. When matched, the
concrete value is bound to `name` and available in subsequent `when`
patterns and in `then` invocations.

```python
# Bind pet_id from the request, carry it into the inventory check
Sync("CheckInventory")
.when(ActionPattern(
    "Web/purchase_request",
    inputs={"pet_id": Var("pet_id")},  # bind pet_id
    outputs={},
))
.then(ActionPattern(
    "Inventory/check",
    inputs={"pet_id": Var("pet_id")},  # use bound pet_id
))
.build()
```

---

### Where clause

The `where` clause is an optional filter or expander between `when` and
`then`. It takes the current variable bindings and returns a list of
binding dicts — one `then` invocation fires per returned dict.

**Critical rules for where clauses:**
- Must be a plain (non-async) function
- Must be pure — no side effects, no `await`, no mutation of external state
- Returns `list[dict]` to expand (fan-out) or filter (return `[]` to skip)

```python
# Pure where clause — expand a collection into individual bindings
def items_to_delete(bindings: dict) -> list[dict]:
    return [
        {**bindings, "item_id": item_id}
        for item_id in bindings["item_ids"]
    ]

# Wrong — mutation inside where clause (R005 violation)
def bad_where(bindings: dict) -> list[dict]:
    cache.append(bindings)       # side effect — forbidden
    return [bindings]
```

---

### Flow

A **flow** is a causally-connected set of action records that all share
the same `flow_token`. Every flow starts with a root action (a self-
completing trigger) and ends when the terminal action (`Web/respond`)
is invoked.

The flow token is generated once at the root and propagated to every
action the engine invokes. It is the mechanism for flow isolation — two
concurrent flows processing the same concept will never cross-match each
other's actions.

---

### Trigger

A **trigger** is the entry point for a flow. It produces the root action
that starts the causal chain.

| Type | Use case |
|---|---|
| `HttpTrigger` | HTTP request → response (blocking) |
| `CliTrigger` | CLI invocation → stdout (blocking) |
| `AsyncLlmTrigger` | LLM response → fire-and-observe (non-blocking) |

`AsyncLlmTrigger` is special: an LLM response arriving out-of-band is a
new causal root, not a downstream sync effect. It emits a root action
with its own `flow_token` and returns immediately.

---

## First Principles of the Sync Engine

The engine design follows ten principles derived from the WYSIWID paper.
They are the foundation that the design rules, linter rules, and contract
invariants all express.

### Principle 1 — Concepts are fully independent

The paper is unambiguous: concepts "have no such dependencies" on each
other. Unlike microservices (which "often end up in a tangle of
dependencies"), a concept may never call another concept's actions or
query another concept's state. All data and control flow between concepts
is expressed *exclusively* in the application layer — the sync layer.

**Corollary:** the engine is the only thing that knows about multiple
concepts. A concept only knows about itself.

---

### Principle 2 — Synchronizations are the sole mechanism of composition

Synchronizations are not a convenience layer on top of some other
composition mechanism. They are *the* mechanism. The paper describes the
alternative — "a procedure for each application endpoint that makes calls
and queries to multiple concepts" — and explicitly presents it as the
naïve prior approach that synchronizations replace. Composition through
direct calls is not a fallback; it's a design failure.

**Corollary:** there should be no place in the codebase where concept A's
output is threaded directly into concept B's input except through a
declared sync rule.

---

### Principle 3 — Synchronizations follow strict causal structure

The paper defines the form precisely: *"when some actions occur under some
conditions, some other actions are invoked."* Three clauses, strictly
ordered:

- **when** — pattern matching on completed action records
- **where** — queries on concept state, plus arbitrary bindings
- **then** — action invocations (not completions — invocations only)

The `then` clause invokes; it does not directly produce outputs. Only
concept execution produces outputs. This is how the engine avoids
conflating orchestration logic with domain logic.

---

### Principle 4 — Flow tokens scope all causal relationships

Every action triggered within a flow shares the same flow token as its
root trigger. This is not optional provenance metadata — it is the
mechanism that:
- prevents syncs from matching actions across unrelated concurrent flows
- provides the audit trail ("each action occurrence can be traced back
  to its causal predecessors")
- enables the debugging workflow in Section 7.4

The paper states this directly: "all cascading synchronizations will
result in a set of causally related actions associated with the same
token."

---

### Principle 5 — Firing idempotency

A given sync fires at most once per `(action_completion, sync_name)`
pair. This is the deduplication guarantee. The paper implements it with
synchronization edges in the action graph: "a synchronization is then
activated only for a particular action completion if there is no existing
outgoing edge... labeled with the synchronization's unique identifier."

This guarantee must hold across engine restarts — the paper explicitly
says the engine "should be able to recover and resume execution
seamlessly" and that "all records [can] be reevaluated on reboot during
failure to resume execution."

---

### Principle 6 — Actions are fully reified as data

From Appendix A.1: "all actions associated with changes in state are fully
reified as data." An action is not an ephemeral function call — it is a
record with an identity, inputs, outputs, a flow token, and a provenance
link to the sync that caused it. This reification is what makes
provenance, auditing, and replay possible.

**Corollary:** the engine's state *is* the action graph. The engine is
not a dispatcher with logs; it is a reactive database of action records
that triggers further invocations.

---

### Principle 7 — Transparency through explicit control flow

"Control flow never passes from one concept to another without an explicit
synchronization, so there is no need to look inside concepts... to figure
out which actions occurred." This is the legibility guarantee the paper's
title refers to. Every behavioral effect is traceable to a named sync
rule.

**Corollary:** unnamed, implicit coordination (callbacks, hidden observers,
side effects in concept code) is a violation of this principle even if it
produces correct behavior.

---

### Principle 8 — State modularity via uninterpreted atoms

Concepts must not embed references to other concepts' schema in their
state declarations. External references are represented as UUIDs —
"uninterpreted atoms" — without any constraints or type knowledge about
what they refer to. This is what makes concepts truly polymorphic and
independently deployable.

**Corollary:** a foreign key typed as another concept's dataclass is a
modularity violation, even if it works.

---

### Principle 9 — The bootstrap concept is the only entry point

All flows originate from a single bootstrap concept (called `Web` in the
paper's case study). It "encapsulates various configuration and
operational concerns" and is "the only one[s] that have completions but
no invocations." Nothing else can start a flow. This keeps entry-point
concerns (HTTP structure, authentication surfaces, protocol specifics)
isolated from domain concepts.

---

### Principle 10 — The engine produces traces as a natural byproduct

Provenance is not instrumentation added after the fact — it falls out of
the architecture. Because every action record carries `caused_by_sync`
and `flow_token`, the full causal DAG of any execution is always
available without any additional logging infrastructure. The paper
demonstrates this in Section 7.4 by using provenance to diagnose the
password registration bug.

---

## Design rules

These rules are the structural expression of the WYSIWID paper's Section 7.2
design rules, translated into Python conventions. Each rule maps to one or
more of the principles above and is enforced by a linter check.

### Rule 1 — Concepts never import concepts

No file in `concepts/` may import from `concepts/` (or from `syncs/`).
All coordination between concepts goes through the sync layer.

```python
# WRONG — concept imports another concept (R001)
from concepts.order import create as order_create

# RIGHT — coordination is expressed as a sync rule, not an import
# (In syncs/purchase.py:)
Sync("PlaceOrder")
.when(ActionPattern("Inventory/check", outputs={"available": True, ...}))
.then(ActionPattern("Order/create", inputs={...}))
.build()
```

**Linter rule:** R001 `no-cross-concept-import`

---

### Rule 2 — External references are uninterpreted atoms

Concept state may not be typed as another concept's dataclass.
Cross-concept references are opaque string identifiers (UUIDs).

```python
# WRONG — couples Inventory schema to Order schema (R002)
@dataclass
class InventoryRecord:
    order: OrderRecord      # foreign concept type

# RIGHT — uninterpreted atom
@dataclass
class InventoryRecord:
    order_id: str           # opaque string; Order concept owns its meaning
```

**Linter rule:** R002 `no-named-foreign-reference`

---

### Rule 3 — Actions must return a dict

An async action function that returns nothing cannot be matched in a
`when` clause. The sync engine never sees it complete.

```python
# WRONG — invisible to the engine (R003)
async def process(inputs: dict):
    do_something(inputs)

# RIGHT
async def process(inputs: dict) -> dict:
    do_something(inputs)
    return {"processed": True}
```

**Linter rule:** R003 `action-returns-void`

---

### Rule 4 — Where clauses are pure reads

The `where` clause is a pure function. It may read bindings and return
new ones, but must not perform any side effect.

```python
# WRONG — mutation inside where (R005)
def expand(bindings: dict) -> list:
    shared_state.append(bindings)   # mutation
    return [bindings]

# WRONG — async operation inside where (R005)
def expand(bindings: dict) -> list:
    async def fetch():
        await get_data()             # nested await
    return [bindings]

# RIGHT — pure read
def expand(bindings: dict) -> list:
    return [{**bindings, "tag": tag} for tag in bindings["tags"]]
```

**Linter rule:** R005 `where-has-side-effects`

---

### Rule 5 — Sync rules reference concepts by namespace string

Sync files do not import concept modules. Concepts are identified by
the `"Concept/action"` namespace string.

```python
# WRONG — sync imports a concept (R001)
from concepts.inventory import check

# RIGHT — reference by namespace string
ActionPattern("Inventory/check", inputs={"pet_id": Var("pid")})
```

This is the structural guarantee that adding or replacing a concept
implementation never requires changing sync files.

---

## The five engine contract invariants

The sync engine guarantees these properties regardless of which storage
backend is used:

1. **Flow isolation** — actions from different concurrent flows never
   cross-match. The `Matcher` filters history to `flow_token` before
   evaluating any pattern.

2. **Firing idempotency** — a sync rule fires at most once per
   `(matched_action_set, sync_name)` pair, even across engine restarts.
   The SQLite backend enforces this via `PRIMARY KEY (from_action_id, sync_name)`
   on the `sync_edges` table.

3. **No cross-concept calls** — the dispatcher routes invocations to
   concept functions; concept functions never call each other.

4. **Provenance completeness** — every non-root `Action` carries
   `caused_by_sync`: the name of the sync rule that invoked it.

5. **Causal ordering** — the engine processes completions in causal order.
   A triggered action's completion cannot be processed before its trigger.

---

## Common mistakes and how the linter catches them

| Mistake | Symptom | Linter rule |
|---|---|---|
| Concept imports another concept | R001 error on `import` statement | R001 |
| State field typed as foreign concept class | R002 error on annotation | R002 |
| Action with no return statement | Sync rule using this action never fires | R003 |
| Action annotated `-> None` | Same | R003 |
| Single-key return, no mutation | Likely a query masquerading as an action | R004 (warning) |
| `await` inside a where clause | Where clause performs async work | R005 |
| `.append()` / `.update()` in where clause | Where clause mutates shared state | R005 |
| Assigning to external dict in where clause | Where clause mutates shared state | R005 |

### Mistakes the linter cannot catch

These require human review:

- **Typo in namespace string** — `"Inventry/check"` silently never
  matches. The engine logs no error; the sync rule simply never fires.
  Check the trace reader output if a rule appears to be missing.

- **Concept calling an external HTTP API** — not prohibited by any rule,
  but may violate concept independence depending on the context. A concept
  that calls another service's API is coupling to that service's interface,
  which has the same risks as coupling to another concept.

- **Where clause that is technically pure but semantically wrong** — a
  where clause that reads from a module-level constant is fine; one that
  reads from a shared mutable variable is a latent bug. The linter cannot
  tell the difference.

---

## The AI-assisted development pipeline

The full pipeline for generating and verifying a new concept:

```
1. Prompt
   "Add a Notification concept with a send action that takes user_id
   and message and returns sent=True and notification_id."

2. Generate
   Agent writes examples/petstore/concepts/notification.py

3. Verify
   python -m linter.cli examples/petstore/concepts/notification.py
   → must exit 0 with zero violations

4. Wire
   Agent adds to examples/petstore/app.py:
     dispatcher.register_action("Notification/send", notification.send)

5. Add sync rule (if needed)
   Agent writes a Sync rule in examples/petstore/syncs/<feature>.py
   python -m linter.cli examples/petstore/syncs/<feature>.py
   → must exit 0

6. Test
   python -m pytest tests/ --asyncio-mode=auto -q
   → all tests must pass

7. Diagnose (if something is wrong)
   python trace/cli.py <flow_token> --db legible.db
   → inspect the causal tree; find the missing or mis-firing sync
```

Steps 3 and 5 are gates. Do not proceed past them if the linter fails.

---

## Quick reference: namespace conventions

| Concept | Namespace prefix | Example action |
|---|---|---|
| Inventory | `Inventory` | `Inventory/check` |
| Order | `Order` | `Order/create` |
| Billing | `Billing` | `Billing/charge` |
| Web (response) | `Web` | `Web/respond` |
| Web (request trigger) | `Web` | `Web/purchase_request` |
| LLM (async trigger) | `Llm` | `Llm/response` |

New concepts follow the same pattern: `ConceptName/action_name`.
Use PascalCase for the concept name, snake_case for the action name.

---

*Last updated: July 2026 — Milestone 4.3*
*See also: ../AGENTS.md (operational), PROJECT_LAYOUT.md (structure), ROADMAP.md (history)*
