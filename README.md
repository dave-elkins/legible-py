# LegiblePy

A Python implementation of the WYSIWID (What You See Is What It Does)
sync engine for Concept Design.

## Installation

```bash
pip install legible-py
```

## Quick Start

```python
from legible.engine import Sync, ActionPattern, Var

# Define sync rules
rule = (
    Sync("Greet")
    .when(ActionPattern("Web/hello", outputs={}))
    .then(ActionPattern("Web/respond", inputs={"message": "Hello, world!"}))
    .build()
)
```

## CLI

```bash
lgbl lint path/to/concept.py
lgbl trace <flow_token> --db legible.db
```

## Documentation

See `AGENTS.md`, `docs/PROJECT_LAYOUT.md`, and `docs/concept-design.md`.
