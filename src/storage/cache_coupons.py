from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from src.config import settings
from src.storage.db import connect


@dataclass(frozen=True, slots=True)
class ScheduledCoupon:
    figi: str
    coupon_date: date
    fix_date: date | None
    pay_one_bond: float
    currency: str | None


async def get(figi: str) -> list[ScheduledCoupon] | None:
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=settings.dividends_ttl_hours)
    ).isoformat()
    async with connect() as conn:
        cur = await conn.execute(
            """
            SELECT coupon_date, fix_date, pay_one_bond, currency, fetched_at
            FROM coupon_schedule_cache
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
        ScheduledCoupon(
            figi=figi,
            coupon_date=date.fromisoformat(r["coupon_date"]),
            fix_date=date.fromisoformat(r["fix_date"]) if r["fix_date"] else None,
            pay_one_bond=r["pay_one_bond"],
            currency=r["currency"],
        )
        for r in rows
    ]


async def replace(figi: str, items: list[ScheduledCoupon]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with connect() as conn:
        await conn.execute("DELETE FROM coupon_schedule_cache WHERE figi = ?", (figi,))
        await conn.executemany(
            """
            INSERT INTO coupon_schedule_cache
                (figi, coupon_date, fix_date, pay_one_bond, currency, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    figi,
                    c.coupon_date.isoformat(),
                    c.fix_date.isoformat() if c.fix_date else None,
                    c.pay_one_bond,
                    c.currency,
                    now,
                )
                for c in items
            ],
        )
        await conn.commit()
