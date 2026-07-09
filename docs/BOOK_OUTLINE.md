# Building Legible Software
## A Practical Guide to the WYSIWID Pattern in Python

*Working outline — June 2026*

---

## About this book

This book builds a working Python sync engine from first principles,
following the architecture described in Meng & Jackson's
*"What You See Is What It Does: A Structural Pattern for Legible Software"*
(Onward! 2025). Every chapter produces a working artifact. Every design
decision is documented as it is made.

The running demonstration is a Pet Store application. By the end of the
book it has a working HTTP API, a CLI, an async LLM integration, a SQLite
persistence layer, a causal trace reader, a static linter, and a canonical
project structure — all built from a small, principled core.

The intended reader has working Python experience and has felt the pain
of a codebase that is hard to change without breaking things. No prior
knowledge of Concept Design or formal methods is assumed.

---

## Part I — The Intellectual Background

*What problem are we solving, and why hasn't it been solved before?*

### Chapter 1 — The Legibility Problem

The central claim: most software is illegible. There is no direct
correspondence between what a user observes and what the code does.
Adding a feature requires understanding far more code than the feature
touches. LLMs have made this worse by accelerating the production of
illegible code while doing nothing to improve its structure.

- The three requirements the paper names: incrementality, integrity, transparency
- Why modularity alone is not enough — the RealWorld benchmark evidence
- The "what gets better?" test for any architectural approach
- Why now: LLMs as both the problem and the motivation for the solution

### Chapter 2 — Concepts and What They Are Not

Daniel Jackson's Concept Design, explained from the outside in. What is
a concept? Why is it not a class, not a microservice, not a domain entity,
not an aggregate? The key move: a concept is defined by its purpose, not
by its data.

- The Upvote concept as the canonical example
- Concepts vs. classes: why OO conflates what concepts separate
- The operational principle: a concept's contract with the user
- Familiar concepts: why applications are usable (users bring concepts from prior experience)
- The reusability insight: the same concept appears across applications

### Chapter 3 — Synchronizations and the Mediator Idea

If concepts are independent, something must coordinate them. That something
is synchronizations. This chapter traces the intellectual lineage from
Sullivan & Notkin's 1992 Mediators paper through Behavioral Programming
(Harel) to the WYSIWID sync scheme.

- Sullivan & Notkin: the first formal treatment of mediators
- Behavioral Programming: b-threads and the coordinated-independence pattern
- The WYSIWID scheme: when/where/then as a declarative coordination language
- Why transactions were abandoned and what replaced them
- The granularity insight: one sync per behavioral rule

### Chapter 4 — The Paper's Case Study and Its Open Threads

A close reading of the RealWorld benchmark case study. What the paper
demonstrates, what it claims but does not show, and what it explicitly
leaves open. This chapter establishes the agenda for the rest of the book.

- The RealWorld benchmark: what it tests and why it is useful
- What the paper built (TypeScript, RDF, SPARQL) and what it did not
- The seven open threads (from the project ideas analysis):
  - No Python implementation
  - No concept catalog
  - Granularity vs. comprehensibility tension (unresolved)
  - Pure function storage (prototyped, unpublished)
  - HTTP-only bootstrap concept
  - LLM over-enthusiasm in concept generation
  - No frontend integration
- The agenda: this book closes threads 1, 3, 4, 5, and 6

---

## Part II — Building the Engine

*A working sync engine, built from contract to implementation.*

### Chapter 5 — What the Engine Must Guarantee

Before writing code, write the contract. Five invariants that any correct
sync engine must satisfy, regardless of storage backend or programming
language. This chapter is the spec for both the implementation and the
test suite.

- Flow isolation: the flow token as causal scope
- Firing idempotency: why "exactly once" requires a key, not a flag
- No cross-concept calls: structural enforcement vs. convention
- Provenance completeness: `caused_by_sync` as the audit trail
- Causal ordering: why completions must be processed in sequence
- Writing the contract before the code: the lab-notebook discipline

### Chapter 6 — Core Data Structures

The `Action` dataclass as the unit of reification. Every occurrence —
invocation and completion — is a record with an identity. The sync DSL:
`ActionPattern`, `Var`, `SyncRule`, the `Sync` builder. The `Matcher`.

- Actions as data, not calls: what reification means and why it matters
- The invocation/completion distinction: outputs=None as a first-class state
- `flow_token`: generated once, propagated everywhere
- `caused_by_sync`: None only for root triggers
- The Sync DSL: when/where/then in Python
- `Var` as an uninterpreted binding variable

### Chapter 7 — A Design Decision Worth Naming

The idempotency key. The ROADMAP originally specified `(action_record_id, sync_name)`
as the deduplication key. This was wrong. Discovering why — and what the
correct key is — is a lesson in why design decisions need to be named and
tested, not just assumed.

- What the wrong key does: re-fires on every new completion
- The correct key: `"__".join(sorted(matched_ids))`
- Why "matched action set + sync name" is the right invariant
- Writing the test that catches the wrong key before it ships
- The lab-notebook principle: wrong decisions deserve documentation too

### Chapter 8 — The In-Memory Engine

`SyncEngine`, `InMemoryFlowStore`, `InMemoryBus`, `AppDispatcher`,
`FlowGateway`. The engine as a reactive system: subscribe, process,
match, fire, dispatch. The fanout bus: why a single-consumer queue
broke the gateway.

- The bus architecture: from single queue to per-subscriber fanout
- The dispatcher: publish invocation before executing concept
- The gateway: resolving futures on terminal action invocation
- Root triggers as self-completing actions: the bootstrapping pattern
- Running the Pet Store for the first time

### Chapter 9 — Three Principles, One Migration

Migrating from in-memory to SQLite. Three first-principles gaps that the
in-memory backend leaves open — firing idempotency on restart, durable
action reification, queryable traces — and how a single schema migration
closes all three.

- The two-table schema: `action_records` and `sync_edges`
- `PRIMARY KEY (from_action_id, sync_name)`: idempotency at the DB level
- `INSERT OR IGNORE` as atomic check-and-insert
- `retain_history=True`: archive vs. delete on flow close
- `completed_action_records`: the trace reader's foundation
- Running the same 23 contract tests against both backends

---

## Part III — Extending the Engine

*Two architectural extensions that address gaps the paper left open.*

### Chapter 10 — Two Kinds of Entry Point

The paper's bootstrap concept is hardcoded to HTTP. Every application has
at least two entry points (HTTP and CLI) and modern applications have a
third: asynchronous LLM responses. This chapter builds the Trigger
abstraction and discovers that two protocols are needed, not one.

- Why the single `Trigger` protocol failed: request/reply vs. fire-and-observe
- `HttpTrigger`: the gateway pattern as a named, reusable object
- `CliTrigger`: owning the event loop with `asyncio.run()`
- The FastAPI endpoint before and after: fifteen lines to four
- LLM responses are root actions, not downstream effects

### Chapter 11 — LLM Responses Are Root Actions

`AsyncLlmTrigger` in depth. Why an LLM response arriving out-of-band
is a new causal root, not a side effect of an existing flow. What
keeping the causal graph acyclic actually means in practice. The
`on_complete` callback as the bridge between fire-and-observe and
whatever the application needs to do with the result.

- The async problem in LLM-integrated applications
- Why treating the LLM response as a sync effect is wrong
- `emit()` vs. `fire()`: the interface difference and what it signals
- The `on_complete` callback: async or sync, called once per flow
- Testing multiple concurrent LLM flows in isolation

### Chapter 12 — Pure Function Storage (the Unpublished Contribution)

Section 9 of the paper describes a storage variant where concepts become
pure functions and a `Store` concept handles all persistence via sync rules.
It was "successfully prototyped" but never published. This chapter
publishes it.

- The signature change: `(inputs) -> dict` to `(state, inputs) -> (state, dict)`
- The `Store` concept: persistence as a domain event, not a side effect
- What this enables: concepts testable as pure functions, no mocks needed
- The dispatcher change: injecting state before calling the concept
- The tradeoff: simpler testing, more complex wiring

---

## Part IV — Tooling

*Making the engine's properties visible and exploitable.*

### Chapter 13 — Reading the Causal Record

The trace reader. Taking the `caused_by_sync` field on every action and
turning it into a human-readable causal tree. Two output formats: terminal
tree for debugging, JSON DAG for downstream tools. The legibility metric:
depth and fan-out as measurable properties of a flow's design.

- Reconstruction from flat records: `caused_by_sync` as the parent pointer
- The builder algorithm: why insertion order is sufficient for disambiguation
- `render_tree()`: Unicode box-drawing, ANSI colour, the sync label placement
- `render_json()`: the foundation for the React DAG artifact
- The CLI: prefix matching, `--list`, `--format json`
- Depth > N, fan-out > M: the first legibility metrics

### Chapter 14 — How to Keep Concepts Clean

The concept linter. Five rules, pure Python AST, no dependencies. Why
false positives from infrastructure code are a signal about structure, not
noise. The moment the linter found a genuine concept design issue in the
Pet Store's own `web.py`.

- R001: concepts importing concepts — the structural violation
- R002: foreign type references — schema coupling disguised as typing
- R003: void actions — invisible to the sync engine
- R004: getter smell — queries masquerading as actions (warning level)
- R005: where-clause side effects — closing the last first-principles gap
- `--format json` for CI and LLM pipeline integration
- What the linter cannot check: namespace typos, semantic violations

### Chapter 15 — What the Linter Tells You

Running `conceptlint` on the Pet Store's original `app.py` for the first
time. Three false positives and one genuine finding. Why the false positives
were the correct signal: they revealed that concept functions, sync rules,
trigger wiring, and FastAPI lifecycle code were all mixed in a single file.
The linter does not know the difference — but the violations it produces
are the exact violations that would exist if the mixing were intentional.

- The original `app.py`: four concerns in one file
- Reading the linter output: which violations are real, which are structural
- The false positive as diagnostic: what it tells you about the architecture
- The genuine finding: `mock_web_respond` as a no-op stub with no domain meaning
- The decision to fix the structure rather than suppress the rules

---

## Part V — Structure

*What the architecture looks like when it is laid out properly.*

### Chapter 16 — Where Things Live

The canonical project layout. Three layers, each with precise rules about
what belongs there and what does not. The linter verification matrix: a
`conceptlint` command for each layer, expected to exit 0. What the layout
cannot enforce statically.

- The three-layer rule: concepts, syncs, wiring
- The dependency direction: wiring imports both; neither imports the other
- `concepts/<name>.py`: what is allowed and what is prohibited
- `syncs/<feature>.py`: namespace strings, not concept imports
- `app.py`: the one file that is allowed to mix concerns
- The verification matrix: linter commands as acceptance criteria

### Chapter 17 — The Refactor the Linter Demanded

The Pet Store refactor. Before and after. Concept functions renamed,
moved to `concepts/`, tested in isolation. Sync rules extracted to
`syncs/purchase.py`. `app.py` reduced to wiring. `cli.py` as a
self-contained second entry point. The acceptance criterion: `conceptlint
examples/petstore/concepts/*.py` exits 0.

- The before: `check_inventory`, `create_order`, `charge_billing` in `app.py`
- The rename: `check_inventory` → `Inventory/check` in `concepts/inventory.py`
- The extraction: six sync rules into `syncs/purchase.py`
- The new `app.py`: twelve lines of wiring, nothing else
- The new test: `TestConceptsInIsolation` — no engine, no mocks, no fixtures
- The 20 new tests and what they prove

### Chapter 18 — Orienting an AI Coding Agent

`../AGENTS.md` and `concept-design.md`. What an AI coding agent needs to
know before generating code in a LegiblePy project. The operational/
educational split: one document for every task, one for understanding
the model. The complete pipeline from prompt to deployed feature.

- What ../AGENTS.md answers: where, what commands, what not to do
- What concept-design.md answers: what things are, why rules exist
- The seven-step pipeline: prompt → generate → lint → wire → test → run → trace
- The lint gate: `conceptlint` must exit 0 before wiring
- The trace gate: if something is wrong, the trace reader shows what
- Why the pipeline closes the loop the paper opened in Section 7.3

---

## Part VI — The Bigger Picture

*What this all means for software design and AI-assisted development.*

### Chapter 19 — What WYSIWID Gets Right (and What It Doesn't)

An honest assessment of the pattern. Where it delivers on its promises —
incrementality, integrity, transparency. Where it struggles — granularity
vs. comprehensibility, the cold-start problem for concept catalogs, the
still-open question of UI integration. What LegiblePy adds to the paper's
contribution.

- The three properties revisited: how does the Pet Store score on each?
- The granularity tension: what the trace reader reveals about sync design
- What the paper's RealWorld case study looked like before vs. after
- The concept catalog future: Section 9 as an open invitation
- What LegiblePy contributes that the paper does not: Python, contract tests,
  archival, triggers, linter, structure

### Chapter 20 — Concept Design in the Age of LLMs

The book's closing argument. LLMs do not solve the legibility problem —
they accelerate it. But a legible architecture changes the relationship
between a human and an LLM collaborator: the human specifies concepts,
the LLM generates them, the linter verifies them, the trace reader
diagnoses them. This is a different kind of AI-assisted development than
"vibe coding."

- Why illegible code is a worse problem with LLMs than without
- The WYSIWID paper's framing: specs are back, even if they're called prompts
- What the LLM generates in a LegiblePy project: concept functions and sync rules
- What the LLM cannot generate: the contract, the architecture, the design decisions
- The division of labour: human designs concepts, LLM implements them, linter verifies
- The open question: concept catalogs as the next frontier

---

## Appendices

### Appendix A — The WYSIWID Paper: Annotated Summary

A section-by-section summary of Meng & Jackson (Onward! 2025) with annotations
noting where LegiblePy follows the paper, where it diverges, and where it
extends beyond it. Intended as a companion for readers who have the paper
in hand.

### Appendix B — Engine Contract Reference

The five invariants stated formally, with the corresponding test cases
from `tests/test_contract.py` and the storage-backend methods that
enforce each one.

### Appendix C — Linter Rule Reference

All five rules (R001–R005) with: what the rule detects, the AST pattern
it looks for, the correct fix, and the test case that verifies it. R006
(deferred) documented with the prerequisite that would unblock it.

### Appendix D — The Pet Store in Full

The complete Pet Store application at the end of the book:
`examples/petstore/concepts/`, `examples/petstore/syncs/`, `examples/petstore/app.py`,
`examples/petstore/cli.py`. Annotated to show which design decisions from the
book each file expresses.

### Appendix E — Intellectual Lineage

The intellectual genealogy of Concept Design and WYSIWID: Parnas on
information hiding (1972), Stevens/Myers/Constantine on coupling and
cohesion (1974), Sullivan & Notkin on mediators (1992), Reenskaug on
MVC (1979), Harel on Behavioral Programming, Jackson on Concept Design
(*The Essence of Software*, 2021), and the WYSIWID paper (2025).
Each entry states the contribution and its relationship to LegiblePy.

---

## Structural notes

**Format:** Each chapter in Parts II–V opens with the chapter's artifact
(a file, a test class, a CLI command, a document), shows the "before" state
of the Pet Store, builds the artifact, and ends with the "after" state.
Design decisions are documented in the text as they are made, not
retrospectively. Wrong decisions are included when they are instructive
(Chapter 7 is built around one).

**Code:** All code is from the actual LegiblePy codebase. No pseudocode,
no simplified examples that diverge from the real implementation.

**Tests:** Every chapter in Parts II–V ends with the test suite state —
how many tests, what they cover, what invariant they verify. The test
count is a progress indicator for the reader.

**Length target:** ~90,000 words. Parts I and VI together ~25,000;
Parts II–V ~50,000; Appendices ~15,000.

---

*Outline version: June 2026*
*Companion documents: ROADMAP.md, PROJECT_LAYOUT.md, ../AGENTS.md, concept-design.md*
