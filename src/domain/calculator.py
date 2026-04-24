from __future__ import annotations

from datetime import date, datetime, timezone

from src.domain.models import AssetReport, DividendEvent, Purchase, Sale
from src.storage import cache_instruments
from src.storage.cursor_store import CachedOperation


def _collect(
    ops: list[CachedOperation],
) -> tuple[list[Purchase], list[Sale], list[DividendEvent]]:
    purchases: list[Purchase] = []
    sales: list[Sale] = []
    dividends_by_date: dict[date, DividendEvent] = {}

    for op in ops:
        if op.type == "BUY" and op.qty and op.price:
            purchases.append(
                Purchase(
                    date=op.date,
                    qty=op.qty,
                    price=op.price,
                    account_id=op.account_id,
                )
            )
        elif op.type == "SELL" and op.qty:
            sales.append(Sale(date=op.date, qty=op.qty, account_id=op.account_id))
        elif op.type == "DIVIDEND" and op.payment:
            # T-Bank возвращает дату зачисления. Для MVP считаем её же "датой события".
            # При наличии явного record_date в ответах GetOperations — можно улучшить.
            rec = op.date.date()
            ev = dividends_by_date.get(rec)
            if ev is None:
                dividends_by_date[rec] = DividendEvent(
                    record_date=rec,
                    pay_date=op.date,
                    amount=op.payment,
                    currency=op.currency,
                )
            else:
                ev.amount += op.payment

    purchases.sort(key=lambda p: p.date)
    sales.sort(key=lambda s: s.date)
    events = sorted(dividends_by_date.values(), key=lambda d: d.record_date)
    return purchases, sales, events


def _apply_fifo_sales(purchases: list[Purchase], sales: list[Sale]) -> list[float]:
    """Для каждой покупки считает остаток на «сейчас» (qty_remaining)."""
    remaining = [p.qty for p in purchases]
    for sale in sales:
        qty_to_sell = sale.qty
        for i in range(len(purchases)):
            if remaining[i] <= 0:
                continue
            if purchases[i].date > sale.date:
                break
            take = min(remaining[i], qty_to_sell)
            remaining[i] -= take
            qty_to_sell -= take
            if qty_to_sell <= 0:
                break
    return remaining


def _snapshot_qty_at(
    purchases: list[Purchase],
    sales: list[Sale],
    at: date,
) -> list[float]:
    """FIFO-состояние лотов на конкретную дату (end-of-day включительно)."""
    snapshot = [
        p.qty if p.date.date() <= at else 0.0
        for p in purchases
    ]
    for sale in sales:
        if sale.date.date() > at:
            continue
        qty_to_sell = sale.qty
        for i in range(len(purchases)):
            if snapshot[i] <= 0:
                continue
            if purchases[i].date > sale.date:
                break
            take = min(snapshot[i], qty_to_sell)
            snapshot[i] -= take
            qty_to_sell -= take
            if qty_to_sell <= 0:
                break
    return snapshot


def _attribute_dividends(
    purchases: list[Purchase],
    sales: list[Sale],
    events: list[DividendEvent],
) -> None:
    """Каждый лот получает долю фактической выплаты пропорционально qty на record_date."""
    for ev in events:
        snap = _snapshot_qty_at(purchases, sales, ev.record_date)
        total_qty = sum(snap)
        if total_qty <= 0:
            continue
        per_share = ev.amount / total_qty
        for i, qty_at in enumerate(snap):
            if qty_at <= 0:
                continue
            purchases[i].qty_at_record[ev.record_date] = qty_at
            purchases[i].received_dividends += qty_at * per_share


def _future_confirmed(
    purchases: list[Purchase],
    remaining: list[float],
    future_per_share: list[tuple[date, float]],
) -> float:
    """Будущий подтверждённый дивиденд считаем по текущим открытым лотам."""
    today = datetime.now(timezone.utc).date()
    total_open_qty = sum(
        r for r, p in zip(remaining, purchases) if p.date.date() <= today
    )
    if total_open_qty <= 0:
        return 0.0
    return sum(per_share for _, per_share in future_per_share) * total_open_qty


async def build_asset_report(
    figi: str,
    ops: list[CachedOperation],
    future_dividends_per_share: list[tuple[date, float]],
) -> AssetReport:
    purchases, sales, events = _collect(ops)
    _attribute_dividends(purchases, sales, events)
    remaining = _apply_fifo_sales(purchases, sales)

    share = await cache_instruments.get_by_figi(figi)
    ticker = share.ticker if share else figi
    name = share.name if share else figi
    currency = share.currency if share else (events[0].currency if events else None)

    total_cost = sum(p.cost for p in purchases)
    total_received = sum(p.received_dividends for p in purchases)
    future = _future_confirmed(purchases, remaining, future_dividends_per_share)
    total_with_future = total_received + future

    purchases_desc = sorted(purchases, key=lambda p: p.date, reverse=True)

    return AssetReport(
        figi=figi,
        ticker=ticker,
        name=name,
        currency=currency,
        total_cost=total_cost,
        total_received=total_received,
        total_with_future=total_with_future,
        future_confirmed=future,
        purchases=purchases_desc,
    )
