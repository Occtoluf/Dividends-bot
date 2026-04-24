from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from src.config import settings
from src.storage.db import connect


@dataclass(frozen=True, slots=True)
class ScheduledDividend:
    figi: str
    record_date: date
    payment_date: date | None
    amount_per_share: float
    currency: str | None


async def get(figi: str) -> list[ScheduledDividend] | None:
    """Возвращает кэш, если он свежий; иначе None — нужно подтянуть из API."""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=settings.dividends_ttl_hours)
    ).isoformat()
    async with connect() as conn:
        cur = await conn.execute(
            """
            SELECT record_date, payment_date, amount_per_share, currency, fetched_at
            FROM dividend_schedule_cache
            WHERE figi = ?
            """,
            (figi,),
        )
        rows = await cur.fetchall()
    if not rows:
        return None
    if any(r["fetched_at"] < cutoff for r in rows):
        return None
    return [
        ScheduledDividend(
            figi=figi,
            record_date=date.fromisoformat(r["record_date"]),
            payment_date=date.fromisoformat(r["payment_date"]) if r["payment_date"] else None,
            amount_per_share=r["amount_per_share"],
            currency=r["currency"],
        )
        for r in rows
    ]


async def replace(figi: str, items: list[ScheduledDividend]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with connect() as conn:
        await conn.execute("DELETE FROM dividend_schedule_cache WHERE figi = ?", (figi,))
        await conn.executemany(
            """
            INSERT INTO dividend_schedule_cache
                (figi, record_date, payment_date, amount_per_share, currency, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    figi,
                    d.record_date.isoformat(),
                    d.payment_date.isoformat() if d.payment_date else None,
                    d.amount_per_share,
                    d.currency,
                    now,
                )
                for d in items
            ],
        )
        await conn.commit()
