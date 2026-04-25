from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from src.config import settings
from src.storage.db import connect


@dataclass(frozen=True, slots=True)
class Bond:
    figi: str
    ticker: str
    name: str
    currency: str | None
    lot: int | None
    nominal: float
    maturity_date: date | None


_META_KEY = "bond_catalog_last_refresh"


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


async def replace_all(bonds: list[Bond]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with connect() as conn:
        await conn.execute("DELETE FROM bond_catalog")
        await conn.executemany(
            """
            INSERT INTO bond_catalog
                (figi, ticker, name, currency, lot, nominal, maturity_date, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    b.figi,
                    b.ticker,
                    b.name,
                    b.currency,
                    b.lot,
                    b.nominal,
                    b.maturity_date.isoformat() if b.maturity_date else None,
                    now,
                )
                for b in bonds
            ],
        )
        await _set_meta(conn, _META_KEY, now)
        await conn.commit()


def _row_to_bond(row) -> Bond:
    return Bond(
        figi=row["figi"],
        ticker=row["ticker"],
        name=row["name"],
        currency=row["currency"],
        lot=row["lot"],
        nominal=row["nominal"] or 0.0,
        maturity_date=date.fromisoformat(row["maturity_date"]) if row["maturity_date"] else None,
    )


async def list_all() -> list[Bond]:
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT figi, ticker, name, currency, lot, nominal, maturity_date FROM bond_catalog"
        )
        rows = await cur.fetchall()
    return [_row_to_bond(r) for r in rows]


async def get_by_figi(figi: str) -> Bond | None:
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT figi, ticker, name, currency, lot, nominal, maturity_date FROM bond_catalog WHERE figi = ?",
            (figi,),
        )
        row = await cur.fetchone()
    return _row_to_bond(row) if row else None


async def get_by_ticker(ticker: str) -> Bond | None:
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT figi, ticker, name, currency, lot, nominal, maturity_date FROM bond_catalog WHERE ticker = ? COLLATE NOCASE",
            (ticker,),
        )
        row = await cur.fetchone()
    return _row_to_bond(row) if row else None
