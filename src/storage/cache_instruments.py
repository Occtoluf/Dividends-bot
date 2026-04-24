from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.config import settings
from src.storage.db import connect


@dataclass(frozen=True, slots=True)
class Share:
    figi: str
    ticker: str
    name: str
    name_en: str | None
    currency: str | None
    lot: int | None


_META_KEY = "catalog_last_refresh"


async def _get_meta(conn, key: str) -> str | None:
    cur = await conn.execute("SELECT value FROM catalog_meta WHERE key = ?", (key,))
    row = await cur.fetchone()
    return row["value"] if row else None


async def _set_meta(conn, key: str, value: str) -> None:
    await conn.execute(
        """
        INSERT INTO catalog_meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


async def is_fresh() -> bool:
    async with connect() as conn:
        val = await _get_meta(conn, _META_KEY)
    if not val:
        return False
    last = datetime.fromisoformat(val)
    return datetime.now(timezone.utc) - last < timedelta(hours=settings.catalog_ttl_hours)


async def replace_all(shares: list[Share]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with connect() as conn:
        await conn.execute("DELETE FROM share_catalog")
        await conn.executemany(
            """
            INSERT INTO share_catalog
                (figi, ticker, name, name_en, currency, lot, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (s.figi, s.ticker, s.name, s.name_en, s.currency, s.lot, now)
                for s in shares
            ],
        )
        await _set_meta(conn, _META_KEY, now)
        await conn.commit()


async def list_all() -> list[Share]:
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT figi, ticker, name, name_en, currency, lot FROM share_catalog"
        )
        rows = await cur.fetchall()
    return [
        Share(
            figi=r["figi"],
            ticker=r["ticker"],
            name=r["name"],
            name_en=r["name_en"],
            currency=r["currency"],
            lot=r["lot"],
        )
        for r in rows
    ]


async def get_by_figi(figi: str) -> Share | None:
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT figi, ticker, name, name_en, currency, lot FROM share_catalog WHERE figi = ?",
            (figi,),
        )
        row = await cur.fetchone()
    if not row:
        return None
    return Share(
        figi=row["figi"],
        ticker=row["ticker"],
        name=row["name"],
        name_en=row["name_en"],
        currency=row["currency"],
        lot=row["lot"],
    )


async def get_by_ticker(ticker: str) -> Share | None:
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT figi, ticker, name, name_en, currency, lot FROM share_catalog WHERE ticker = ? COLLATE NOCASE",
            (ticker,),
        )
        row = await cur.fetchone()
    if not row:
        return None
    return Share(
        figi=row["figi"],
        ticker=row["ticker"],
        name=row["name"],
        name_en=row["name_en"],
        currency=row["currency"],
        lot=row["lot"],
    )
