from __future__ import annotations

import json
import logging
from typing import List, Optional

import aiosqlite

from .models import Action

logger = logging.getLogger("wysiwid.store_sqlite")

_COLUMNS = "(id, concept, action, inputs, outputs, flow_token, caused_by_sync)"

_DDL = """
CREATE TABLE IF NOT EXISTS action_records (
    id             TEXT PRIMARY KEY,
    concept        TEXT NOT NULL,
    action         TEXT NOT NULL,
    inputs         TEXT NOT NULL,
    outputs        TEXT,
    flow_token     TEXT NOT NULL,
    caused_by_sync TEXT
);

CREATE INDEX IF NOT EXISTS idx_ar_flow
    ON action_records (flow_token);

CREATE TABLE IF NOT EXISTS completed_action_records (
    id             TEXT PRIMARY KEY,
    concept        TEXT NOT NULL,
    action         TEXT NOT NULL,
    inputs         TEXT NOT NULL,
    outputs        TEXT,
    flow_token     TEXT NOT NULL,
    caused_by_sync TEXT
);

CREATE INDEX IF NOT EXISTS idx_car_flow
    ON completed_action_records (flow_token);

CREATE TABLE IF NOT EXISTS sync_edges (
    from_action_id  TEXT NOT NULL,
    sync_name       TEXT NOT NULL,
    to_action_id    TEXT NOT NULL,
    PRIMARY KEY (from_action_id, sync_name)
);
"""


def _split_namespace(namespace: str):
    if "/" in namespace:
        concept, _, action = namespace.partition("/")
        return concept, action
    return namespace, ""


def _action_from_row(row) -> Action:
    concept, action_name = row["concept"], row["action"]
    namespace = f"{concept}/{action_name}" if action_name else concept
    outputs_raw = row["outputs"]
    return Action(
        namespace=namespace,
        inputs=json.loads(row["inputs"]),
        outputs=json.loads(outputs_raw) if outputs_raw is not None else None,
        flow_token=row["flow_token"],
        id=row["id"],
        caused_by_sync=row["caused_by_sync"],
    )


class SQLiteFlowStore:
    def __init__(self, db: aiosqlite.Connection, retain_history: bool) -> None:
        self._db = db
        self._retain = retain_history

    @classmethod
    async def create(
        cls,
        path: str = ":memory:",
        retain_history: bool = True,
    ) -> "SQLiteFlowStore":
        db = await aiosqlite.connect(path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.executescript(_DDL)
        await db.commit()
        mode = "retain" if retain_history else "delete-on-evict"
        logger.info(f"[SQLiteFlowStore] Opened {path!r} (mode={mode})")
        return cls(db, retain_history)

    async def close(self) -> None:
        await self._db.close()

    async def add_action(self, action: Action) -> List[Action]:
        concept, action_name = _split_namespace(action.namespace)
        outputs_json = json.dumps(action.outputs) if action.outputs is not None else None
        await self._db.execute(
            f"""
            INSERT OR IGNORE INTO action_records {_COLUMNS}
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action.id,
                concept,
                action_name,
                json.dumps(action.inputs),
                outputs_json,
                action.flow_token,
                action.caused_by_sync,
            ),
        )
        await self._db.commit()
        return await self.get_history(action.flow_token)

    async def get_history(self, flow_token: str) -> List[Action]:
        async with self._db.execute(
            "SELECT * FROM action_records WHERE flow_token = ? ORDER BY rowid",
            (flow_token,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_action_from_row(r) for r in rows]

    async def record_sync_edge(
        self, from_action_id: str, sync_name: str, to_action_id: str
    ) -> bool:
        cursor = await self._db.execute(
            """
            INSERT OR IGNORE INTO sync_edges (from_action_id, sync_name, to_action_id)
            VALUES (?, ?, ?)
            """,
            (from_action_id, sync_name, to_action_id),
        )
        await self._db.commit()
        return cursor.rowcount == 1

    async def evict_flow(self, flow_token: str) -> None:
        if self._retain:
            await self._db.execute(
                f"""
                INSERT OR IGNORE INTO completed_action_records {_COLUMNS}
                SELECT {_COLUMNS.strip("()")}
                FROM action_records
                WHERE flow_token = ?
                """,
                (flow_token,),
            )
        await self._db.execute(
            "DELETE FROM action_records WHERE flow_token = ?",
            (flow_token,),
        )
        await self._db.commit()
        mode = "archived" if self._retain else "deleted"
        logger.debug(
            f"[SQLiteFlowStore] Flow {flow_token[:8]}… {mode}."
        )

    async def get_completed_history(self, flow_token: str) -> List[Action]:
        async with self._db.execute(
            """
            SELECT * FROM completed_action_records
            WHERE flow_token = ? ORDER BY rowid
            """,
            (flow_token,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_action_from_row(r) for r in rows]

    async def get_any_history(self, flow_token: str) -> List[Action]:
        live = await self.get_history(flow_token)
        if live:
            return live
        return await self.get_completed_history(flow_token)

    async def get_all_flows(self, include_completed: bool = True) -> List[str]:
        tokens: set = set()
        async with self._db.execute(
            "SELECT DISTINCT flow_token FROM action_records"
        ) as cursor:
            for row in await cursor.fetchall():
                tokens.add(row["flow_token"])

        if include_completed:
            async with self._db.execute(
                "SELECT DISTINCT flow_token FROM completed_action_records"
            ) as cursor:
                for row in await cursor.fetchall():
                    tokens.add(row["flow_token"])

        return list(tokens)

    async def get_sync_edges(
        self, from_action_id: Optional[str] = None
    ) -> List[dict]:
        if from_action_id:
            async with self._db.execute(
                "SELECT * FROM sync_edges WHERE from_action_id = ?",
                (from_action_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with self._db.execute("SELECT * FROM sync_edges") as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]
