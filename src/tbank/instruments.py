from __future__ import annotations

from datetime import datetime, timedelta, timezone

from t_tech.invest import InstrumentStatus

from src.storage import cache_bonds, cache_coupons, cache_dividends, cache_instruments
from src.storage.cache_bonds import Bond
from src.storage.cache_coupons import ScheduledCoupon
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


async def refresh_bond_catalog_if_stale() -> None:
    if await cache_bonds.is_fresh():
        return
    async with services() as s:
        # ALL, а не BASE: чтобы находить облигации, которые уже погасились/делистнулись —
        # по ним пользователь может спрашивать прошлые купоны.
        resp = await s.instruments.bonds(
            instrument_status=InstrumentStatus.INSTRUMENT_STATUS_ALL
        )
    bonds = [
        Bond(
            figi=inst.figi,
            ticker=inst.ticker,
            name=inst.name,
            currency=inst.currency,
            lot=inst.lot,
            nominal=money_to_float(inst.nominal),
            maturity_date=inst.maturity_date.date() if inst.maturity_date else None,
        )
        for inst in resp.instruments
    ]
    await cache_bonds.replace_all(bonds)


async def get_future_coupons(figi: str) -> list[ScheduledCoupon]:
    cached = await cache_coupons.get(figi)
    if cached is not None:
        return [c for c in cached if c.coupon_date >= datetime.now(timezone.utc).date()]
    now = datetime.now(timezone.utc)
    # Расписание купонов публикуется далеко вперёд; года достаточно для UI-отчёта.
    to = now + timedelta(days=365)
    async with services() as s:
        resp = await s.instruments.get_bond_coupons(figi=figi, from_=now, to=to)
    items = [
        ScheduledCoupon(
            figi=figi,
            coupon_date=c.coupon_date.date() if c.coupon_date else None,
            fix_date=c.fix_date.date() if c.fix_date else None,
            pay_one_bond=money_to_float(c.pay_one_bond),
            currency=getattr(c.pay_one_bond, "currency", None),
        )
        for c in resp.events
        if c.coupon_date is not None
    ]
    await cache_coupons.replace(figi, items)
    return [c for c in items if c.coupon_date >= now.date()]


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
