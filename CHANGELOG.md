# Changelog

## 0.1.0 — 2026-07-09

Initial release. All planned milestones complete.

### Engine

- Sync engine with `Sync`, `ActionPattern`, `Var` DSL
- `AppDispatcher` + `FlowGateway` for action routing and flow management
- `InMemoryBus` fanout pub/sub with per-subscriber asyncio queues
- `InMemoryFlowStore` and `SQLiteFlowStore` storage backends
- Five contract invariants: flow isolation, firing idempotency,
  no cross-concept calls, provenance completeness, causal ordering
- `HttpTrigger`, `CliTrigger`, `AsyncLlmTrigger` entry points

### Pure Function Variant

- `PureFunctionDispatcher` — drop-in replacement managing state lifecycle
- `ConceptStateStore` protocol with `InMemoryStateStore` and `SqliteStateStore`
- Deterministic, async-free concept functions testable without the engine

### Linter

- Five AST rules: R001 (cross-concept import), R002 (foreign type reference),
  R003 (void action), R004 (getter smell), R005 (where-clause side effects)
- CLI entry point via `lgbl lint` or direct `python -m legible.linter.cli`

### Trace Reader

- `build_trace()` constructs causal DAG from action history
- `render_tree()` and `render_json()` output formats
- CLI entry point via `lgbl trace`
- Prefix matching and `--list` for flow enumeration

### Pet Store Reference Application

- `examples/petstore/` with Inventory, Order, Billing, Web concepts
- Six purchase sync rules covering success, stock, and error paths
- LLM recommendation trigger demonstrating async root actions

### Project

- MIT license
- AGENTS.md, concept-design.md, PROJECT_LAYOUT.md, ROADMAP.md docs
- 141 tests across contract, triggers, trace, linter, and integration suites
