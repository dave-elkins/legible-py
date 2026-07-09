from __future__ import annotations

import argparse
import asyncio
import sys

from ..engine.store_sqlite import SQLiteFlowStore
from .model import build_trace
from .render import render_json, render_tree


async def _resolve_token(flow_token: str, store: SQLiteFlowStore) -> str:
    if len(flow_token) == 32:
        return flow_token
    all_flows = await store.get_all_flows(include_completed=True)
    matches = [t for t in all_flows if t.startswith(flow_token.lower())]
    if not matches:
        raise ValueError(f"No flow found with prefix {flow_token!r}")
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous prefix {flow_token!r} — matches {len(matches)} flows. "
            f"Provide more characters."
        )
    return matches[0]


async def _show_flow(
    flow_token: str,
    db_path: str,
    fmt: str,
    use_colour: bool,
) -> int:
    store = await SQLiteFlowStore.create(db_path, retain_history=True)
    try:
        flow_token = await _resolve_token(flow_token, store)
        history = await store.get_any_history(flow_token)
        if not history:
            print(
                f"No records found for flow {flow_token[:8]}...\n"
                f"(The flow may not exist, or was stored with retain_history=False.)",
                file=sys.stderr,
            )
            return 1

        trace = build_trace(flow_token, history)

        if fmt == "json":
            print(render_json(trace))
        else:
            print(render_tree(trace, use_colour=use_colour))

        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await store.close()


async def _list_flows(db_path: str) -> int:
    store = await SQLiteFlowStore.create(db_path, retain_history=True)
    try:
        flows = await store.get_all_flows(include_completed=True)
        if not flows:
            print("No flows recorded.")
            return 0
        print(f"{len(flows)} flow(s) recorded:")
        for token in flows:
            history = await store.get_any_history(token)
            completions = [a for a in history if a.outputs is not None]
            status = "live" if await store.get_history(token) else "completed"
            root_ns = next(
                (a.namespace for a in completions if a.caused_by_sync is None),
                "unknown",
            )
            print(f"  {token[:8]}...  [{status}]  {root_ns}  ({len(completions)} actions)")
        return 0
    finally:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LegiblePy trace reader — inspect the causal history of a flow.",
    )
    parser.add_argument(
        "flow_token",
        nargs="?",
        help="Flow token to inspect (first 8+ chars are sufficient for --list output).",
    )
    parser.add_argument(
        "--db",
        default="legible.db",
        metavar="PATH",
        help="Path to the SQLite database (default: legible.db).",
    )
    parser.add_argument(
        "--format",
        choices=["tree", "json"],
        default="tree",
        dest="fmt",
        help="Output format: 'tree' (default) or 'json'.",
    )
    parser.add_argument(
        "--no-colour",
        action="store_true",
        help="Disable ANSI colour in tree output.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all recorded flows in the database.",
    )

    args = parser.parse_args()

    if args.list:
        rc = asyncio.run(_list_flows(args.db))
        sys.exit(rc)

    if not args.flow_token:
        parser.error("flow_token is required unless --list is specified.")

    rc = asyncio.run(
        _show_flow(
            flow_token=args.flow_token,
            db_path=args.db,
            fmt=args.fmt,
            use_colour=not args.no_colour,
        )
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
