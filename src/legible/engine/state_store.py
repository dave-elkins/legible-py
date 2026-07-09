from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import asdict, fields, is_dataclass
from typing import Any, Optional, Type, TypeVar

import aiosqlite
from typing_extensions import Protocol, runtime_checkable

logger = logging.getLogger("wysiwid.state_store")

S = TypeVar("S")


@runtime_checkable
class ConceptStateStore(Protocol[S]):
    async def get(self) -> S:
        ...

    async def set(self, state: S) -> None:
        ...


class InMemoryStateStore:
    def __init__(self, initial: Any) -> None:
        self._state = deepcopy(initial)

    async def get(self) -> Any:
        return deepcopy(self._state)

    async def set(self, state: Any) -> None:
        self._state = deepcopy(state)


_DDL = """
CREATE TABLE IF NOT EXISTS concept_states (
    namespace  TEXT PRIMARY KEY,
    state_json TEXT NOT NULL
);
"""


class SqliteStateStore:
    def __init__(
        self,
        db: aiosqlite.Connection,
        namespace: str,
        initial: Any,
        state_type: Optional[Type] = None,
    ) -> None:
        self._db = db
        self._namespace = namespace
        self._initial = initial
        self._state_type = state_type

    @classmethod
    async def create(
        cls,
        path: str,
        namespace: str,
        initial: Any,
        state_type: Optional[Type] = None,
    ) -> "SqliteStateStore":
        db = await aiosqlite.connect(path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.executescript(_DDL)
        await db.commit()
        return cls(db, namespace, initial, state_type)

    async def close(self) -> None:
        await self._db.close()

    async def get(self) -> Any:
        async with self._db.execute(
            "SELECT state_json FROM concept_states WHERE namespace = ?",
            (self._namespace,),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return deepcopy(self._initial)

        data = json.loads(row["state_json"])
        if self._state_type is not None and is_dataclass(self._state_type):
            return _from_dict(self._state_type, data)
        return data

    async def set(self, state: Any) -> None:
        if is_dataclass(state):
            data = asdict(state)
        else:
            data = state
        await self._db.execute(
            """
            INSERT INTO concept_states (namespace, state_json)
            VALUES (?, ?)
            ON CONFLICT(namespace) DO UPDATE SET state_json = excluded.state_json
            """,
            (self._namespace, json.dumps(data)),
        )
        await self._db.commit()


def _from_dict(cls: Type[S], data: dict) -> S:
    if not is_dataclass(cls):
        return data

    kwargs = {}
    for f in fields(cls):
        value = data.get(f.name)
        field_type = f.type

        if isinstance(field_type, str):
            import typing
            field_type = typing.get_type_hints(cls).get(f.name, field_type)

        if (
            value is not None
            and isinstance(value, dict)
            and isinstance(field_type, type)
            and is_dataclass(field_type)
        ):
            kwargs[f.name] = _from_dict(field_type, value)
        else:
            kwargs[f.name] = value

    return cls(**kwargs)
