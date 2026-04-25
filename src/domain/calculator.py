from __future__ import annotations

from datetime import date, datetime, timezone

from src.domain.models import AssetReport, Purchase, Sale
from src.storage import cache_bonds, cache_instruments
from src.storage.cursor_store import CachedOperation


def _collect(
    ops: list[CachedOperation],
    *,
    income_type: str = "DIVIDEND",
) -> tuple[
    list[Purchase],
    list[Sale],
    dict[date, dict[str, float]],
    dict[date, str | None],
    dict[date, datetime],
]:
    """Собирает покупки, продажи и выплаты дохода (dividend/coupon), сгруппированные по (дата, счёт).

    Возвращает per-account payment map, потому что T-Invest для ИИС часто отдаёт только
    налог без самой операции выплаты — нужно уметь взять per-share ставку с брокерского
    счёта и применить её к акциям/облигациям на ИИС.
    """
    purchases: list[Purchase] = []
    sales: list[Sale] = []
    # {record_date: {account_id: net_payment_sum}}
    income_by_date_account: dict[date, dict[str, float]] = {}
    currency_by_date: dict[date, str | None] = {}
    pay_date_by_date: dict[date, datetime] = {}

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
        elif op.type == income_type and op.payment:
            rec = op.date.date()
            by_acc = income_by_date_account.setdefault(rec, {})
            by_acc[op.account_id] = by_acc.get(op.account_id, 0.0) + op.payment
            currency_by_date.setdefault(rec, op.currency)
            prev = pay_date_by_date.get(rec)
            if prev is None or op.date < prev:
                pay_date_by_date[rec] = op.date

    purchases.sort(key=lambda p: p.date)
    sales.sort(key=lambda s: s.date)
    return purchases, sales, income_by_date_account, currency_by_date, pay_date_by_date


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
    div_by_date_account: dict[date, dict[str, float]],
) -> None:
    """Каждый лот получает per-share net × qty на record_date.

    Per-share считаем от счёта, по которому пришла операция DIVIDEND (обычно брокер):
    payment_на_счёт / shares_на_счёт_в_record_date. Эту ставку применяем ко ВСЕМ лотам
    (включая ИИС, где API отдаёт только DIVIDEND_TAX). Так мы реконструируем реальную
    выплату по ИИС-долям, которая не видна напрямую в операциях.
    """
    for rec_date in sorted(div_by_date_account.keys()):
        by_account = div_by_date_account[rec_date]
        snap = _snapshot_qty_at(purchases, sales, rec_date)
        total_qty = sum(snap)
        if total_qty <= 0:
            continue

        per_share: float | None = None
        for acc_id, payment in by_account.items():
            if payment <= 0:
                continue
            shares_on_acc = sum(
                qty for qty, p in zip(snap, purchases)
                if qty > 0 and p.account_id == acc_id
            )
            if shares_on_acc > 0:
                per_share = payment / shares_on_acc
                break

        if per_share is None:
            # Нет ни одного счёта с положительной выплатой (например, фигурирует только
            # налог на ИИС без брокерской DIVIDEND) — реконструировать нечем, пропускаем.
            continue

        for i, qty_at in enumerate(snap):
            if qty_at <= 0:
                continue
            purchases[i].qty_at_record[rec_date] = qty_at
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
    future_per_share: list[tuple[date, float]],
    *,
    income_type: str = "DIVIDEND",
) -> AssetReport:
    purchases, sales, income_by_date_account, currency_by_date, _ = _collect(
        ops, income_type=income_type
    )
    _attribute_dividends(purchases, sales, income_by_date_account)
    remaining = _apply_fifo_sales(purchases, sales)

    ticker = figi
    name = figi
    share_currency: str | None = None
    share = await cache_instruments.get_by_figi(figi)
    if share:
        ticker, name, share_currency = share.ticker, share.name, share.currency
    else:
        bond = await cache_bonds.get_by_figi(figi)
        if bond:
            ticker, name, share_currency = bond.ticker, bond.name, bond.currency

    fallback_currency = next(iter(currency_by_date.values()), None) if currency_by_date else None
    currency = share_currency or fallback_currency

    total_cost = sum(p.cost for p in purchases)
    total_received = sum(p.received_dividends for p in purchases)
    future = _future_confirmed(purchases, remaining, future_per_share)
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
