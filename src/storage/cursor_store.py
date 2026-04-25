from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.storage.db import connect


@dataclass(frozen=True, slots=True)
class CachedOperation:
    account_id: str
    op_id: str
    figi: str | None
    type: str
    date: datetime
    qty: float | None
    price: float | None
    payment: float | None
    currency: str | None


async def get_cursor(account_id: str) -> str | None:
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT cursor FROM operations_cursor WHERE account_id = ? AND figi = ''",
            (account_id,),
        )
        row = await cur.fetchone()
    return row["cursor"] if row else None


async def save_cursor(account_id: str, cursor: str) -> None:
    async with connect() as conn:
        await conn.execute(
            """
            INSERT INTO operations_cursor (account_id, figi, cursor, updated_at)
            VALUES (?, '', ?, ?)
            ON CONFLICT(account_id, figi) DO UPDATE SET
                cursor = excluded.cursor,
                updated_at = excluded.updated_at
            """,
            (account_id, cursor, datetime.now(timezone.utc).isoformat()),
        )
        await conn.commit()


async def upsert_operations(ops: list[CachedOperation]) -> None:
    if not ops:
        return
    async with connect() as conn:
        await conn.executemany(
            """
            INSERT INTO operations_cache
                (account_id, op_id, figi, type, date, qty, price, payment, currency)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, op_id) DO UPDATE SET
                figi     = excluded.figi,
                type     = excluded.type,
                date     = excluded.date,
                qty      = excluded.qty,
                price    = excluded.price,
                payment  = excluded.payment,
                currency = excluded.currency
            """,
            [
                (
                    o.account_id,
                    o.op_id,
                    o.figi,
                    o.type,
                    o.date.isoformat(),
                    o.qty,
                    o.price,
                    o.payment,
                    o.currency,
                )
                for o in ops
            ],
        )
        await conn.commit()


async def load_for_figi(figi: str) -> list[CachedOperation]:
    async with connect() as conn:
        cur = await conn.execute(
            """
            SELECT account_id, op_id, figi, type, date, qty, price, payment, currency
            FROM operations_cache
            WHERE figi = ?
            ORDER BY date ASC
            """,
            (figi,),
        )
        rows = await cur.fetchall()
    return [
        CachedOperation(
            account_id=r["account_id"],
            op_id=r["op_id"],
            figi=r["figi"],
            type=r["type"],
            date=datetime.fromisoformat(r["date"]),
            qty=r["qty"],
            price=r["price"],
            payment=r["payment"],
            currency=r["currency"],
        )
        for r in rows
    ]


async def list_figis_with_income(income_type: str) -> list[str]:
    """Возвращает уникальные figi, по которым есть операция income_type в кэше."""
    async with connect() as conn:
        cur = await conn.execute(
            """
            SELECT DISTINCT figi FROM operations_cache
            WHERE type = ? AND figi IS NOT NULL AND figi != ''
            """,
            (income_type,),
        )
        rows = await cur.fetchall()
    return [r["figi"] for r in rows]


async def last_cached_date(account_id: str) -> datetime | None:
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT MAX(date) AS d FROM operations_cache WHERE account_id = ?",
            (account_id,),
        )
        row = await cur.fetchone()
    if not row or not row["d"]:
        return None
    return datetime.fromisoformat(row["d"])


