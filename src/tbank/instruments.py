from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tinkoff.invest import InstrumentStatus

from src.storage import cache_dividends, cache_instruments
from src.storage.cache_dividends import ScheduledDividend
from src.storage.cache_instruments import Share
from src.tbank.client import money_to_float, services


async def refresh_catalog_if_stale() -> None:
    if await cache_instruments.is_fresh():
        return
    async with services() as s:
        resp = await s.instruments.shares(
            instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
        )
    shares = [
        Share(
            figi=inst.figi,
            ticker=inst.ticker,
            name=inst.name,
            name_en=getattr(inst, "name", None) and None,  # SDK не отдаёт отдельного name_en
            currency=inst.currency,
            lot=inst.lot,
        )
        for inst in resp.instruments
    ]
    await cache_instruments.replace_all(shares)


async def get_future_dividends(figi: str) -> list[ScheduledDividend]:
    cached = await cache_dividends.get(figi)
    if cached is not None:
        return [d for d in cached if d.record_date >= datetime.now(timezone.utc).date()]
    now = datetime.now(timezone.utc)
    # На год вперёд достаточно: T-Bank публикует ближайшие решения собраний.
    to = now + timedelta(days=365)
    async with services() as s:
        resp = await s.instruments.get_dividends(figi=figi, from_=now, to=to)
    items = [
        ScheduledDividend(
            figi=figi,
            record_date=d.record_date.date() if d.record_date else d.last_buy_date.date(),
            payment_date=d.payment_date.date() if d.payment_date else None,
            amount_per_share=money_to_float(d.dividend_net),
            currency=getattr(d.dividend_net, "currency", None),
        )
        for d in resp.dividends
        if d.dividend_net is not None
    ]
    await cache_dividends.replace(figi, items)
    return [d for d in items if d.record_date >= now.date()]
