# Contributing

Thanks for your interest! All contributions — bug reports, docs,
features, tests — are welcome.

---

## Development Setup

```bash
git clone https://github.com/dave-elkins/legible-py.git
cd legible-py
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
python -m pytest tests/ --asyncio-mode=auto -q
```

All tests must pass before submitting a PR.

## Linting

```bash
# Ruff (import sorting, formatting rules)
ruff check src/ tests/ examples/

# Concept linter on example files
python -m legible.linter.cli examples/petstore/concepts/*.py
python -m legible.linter.cli examples/petstore/syncs/*.py
```

Both must exit 0 before submitting.

## Code Conventions

- **Three-layer rule:** concepts live in `concepts/`, sync rules in
  `syncs/`, wiring in `app.py`/`cli.py`. See `docs/PROJECT_LAYOUT.md`.
- **Actions return dict:** every async action function must return a `dict`.
- **No cross-concept imports:** concepts never import other concepts or
  sync modules. See `docs/concept-design.md` §Design rules.
- **Imports sorted:** run `ruff check --fix .` before committing.

## Adding a Concept

1. Create `concepts/<name>.py` with one or more async action functions.
2. Verify with `python -m legible.linter.cli concepts/<name>.py`.
3. Wire into `app.py` via `dispatcher.register_action("Ns/action", handler)`.
4. Add unit tests in `tests/`.

## Adding a Sync Rule

1. Add a `Sync(...).when(...).then(...).build()` call in the appropriate
   `syncs/<feature>.py`.
2. Reference concepts by namespace string only — no imports of concept
   modules.
3. Verify with `python -m legible.linter.cli syncs/<feature>.py`.

## Project Structure

```
src/legible/         — engine, linter, trace packages
examples/petstore/   — reference application
tests/               — test suites
docs/                — design documents and roadmap
```

## Questions?

Open an issue or start a discussion on GitHub.
