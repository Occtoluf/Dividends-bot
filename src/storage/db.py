from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from src.config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS aliases (
    query_norm TEXT PRIMARY KEY,
    figi       TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS share_catalog (
    figi       TEXT PRIMARY KEY,
    ticker     TEXT NOT NULL,
    name       TEXT NOT NULL,
    name_en    TEXT,
    currency   TEXT,
    lot        INTEGER,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_share_catalog_ticker ON share_catalog(ticker);

CREATE TABLE IF NOT EXISTS catalog_meta (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dividend_schedule_cache (
    figi             TEXT NOT NULL,
    record_date      TEXT NOT NULL,
    payment_date     TEXT,
    amount_per_share REAL NOT NULL,
    currency         TEXT,
    fetched_at       TEXT NOT NULL,
    PRIMARY KEY (figi, record_date)
);

CREATE TABLE IF NOT EXISTS operations_cursor (
    account_id TEXT NOT NULL,
    figi       TEXT NOT NULL DEFAULT '',
    cursor     TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, figi)
);

CREATE TABLE IF NOT EXISTS operations_cache (
    account_id TEXT NOT NULL,
    op_id      TEXT NOT NULL,
    figi       TEXT,
    type       TEXT NOT NULL,
    date       TEXT NOT NULL,
    qty        REAL,
    price      REAL,
    payment    REAL,
    currency   TEXT,
    PRIMARY KEY (account_id, op_id)
);
CREATE INDEX IF NOT EXISTS ix_operations_cache_figi ON operations_cache(figi);
"""


_initialised = False


async def _ensure_schema(conn: aiosqlite.Connection) -> None:
    await conn.executescript(SCHEMA)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.commit()


async def init() -> None:
    global _initialised
    path = Path(settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as conn:
        await _ensure_schema(conn)
    _initialised = True


@asynccontextmanager
async def connect() -> AsyncIterator[aiosqlite.Connection]:
    if not _initialised:
        await init()
    async with aiosqlite.connect(settings.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn
