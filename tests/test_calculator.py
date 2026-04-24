from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.domain.calculator import build_asset_report
from src.storage.cache_instruments import Share
from src.storage.cursor_store import CachedOperation


def _dt(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


def _buy(date, qty, price, acc="A") -> CachedOperation:
    return CachedOperation(
        account_id=acc,
        op_id=f"b-{date.isoformat()}-{qty}-{price}-{acc}",
        figi="FIGI",
        type="BUY",
        date=date,
        qty=qty,
        price=price,
        payment=-qty * price,
        currency="rub",
    )


def _sell(date, qty, acc="A") -> CachedOperation:
    return CachedOperation(
        account_id=acc,
        op_id=f"s-{date.isoformat()}-{qty}-{acc}",
        figi="FIGI",
        type="SELL",
        date=date,
        qty=qty,
        price=0.0,
        payment=0.0,
        currency="rub",
    )


def _div(date, amount, acc="A") -> CachedOperation:
    return CachedOperation(
        account_id=acc,
        op_id=f"d-{date.isoformat()}-{amount}-{acc}",
        figi="FIGI",
        type="DIVIDEND",
        date=date,
        qty=None,
        price=None,
        payment=amount,
        currency="rub",
    )


_SHARE = Share(figi="FIGI", ticker="TST", name="TestCo", name_en=None, currency="rub", lot=1)


@pytest.fixture(autouse=True)
def _stub_share_lookup():
    with patch("src.domain.calculator.cache_instruments.get_by_figi", return_value=_SHARE) as m:
        async def _ret(_figi):
            return _SHARE
        m.side_effect = _ret
        yield


@pytest.mark.asyncio
async def test_single_purchase_single_dividend():
    ops = [
        _buy(_dt(2024, 1, 10), 10, 100.0),
        _div(_dt(2024, 6, 1), 50.0),
    ]
    r = await build_asset_report("FIGI", ops, [])
    assert r.total_cost == 1000.0
    assert r.total_received == 50.0
    assert len(r.purchases) == 1
    assert r.purchases[0].received_dividends == 50.0
    assert r.purchases[0].yield_pct == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_two_purchases_pro_rata_on_record_date():
    # Обе покупки жили на record_date => поровну делим дивиденд.
    ops = [
        _buy(_dt(2024, 1, 10), 10, 100.0),
        _buy(_dt(2024, 3, 10), 10, 200.0),
        _div(_dt(2024, 6, 1), 200.0),  # по 10 ₽/акц на 20 акций
    ]
    r = await build_asset_report("FIGI", ops, [])
    a, b = sorted(r.purchases, key=lambda p: p.date)
    assert a.received_dividends == pytest.approx(100.0)
    assert b.received_dividends == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_fifo_sale_before_record_date_strips_oldest_lot():
    # Куплено 10 + 10, потом продано 10 ДО отсечки. FIFO: «съели» первый лот.
    ops = [
        _buy(_dt(2024, 1, 10), 10, 100.0),
        _buy(_dt(2024, 3, 10), 10, 200.0),
        _sell(_dt(2024, 5, 1), 10),
        _div(_dt(2024, 6, 1), 100.0),  # на 10 оставшихся акций => 10 ₽/акц
    ]
    r = await build_asset_report("FIGI", ops, [])
    old = next(p for p in r.purchases if p.price == 100.0)
    new = next(p for p in r.purchases if p.price == 200.0)
    assert old.received_dividends == pytest.approx(0.0)
    assert new.received_dividends == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_full_sale_before_record_yields_no_dividend_attributed():
    ops = [
        _buy(_dt(2024, 1, 10), 10, 100.0),
        _sell(_dt(2024, 5, 1), 10),
        # Дивиденд придёт, но фактическая выплата на этот FIGI отсутствует в ops.
    ]
    r = await build_asset_report("FIGI", ops, [])
    assert r.total_received == 0.0
    assert r.purchases[0].received_dividends == 0.0


@pytest.mark.asyncio
async def test_purchase_after_record_date_gets_zero():
    # Купили уже после отсечки — по ней ничего не должны получать.
    ops = [
        _buy(_dt(2024, 1, 10), 10, 100.0),
        _div(_dt(2024, 6, 1), 50.0),
        _buy(_dt(2024, 7, 1), 10, 120.0),
    ]
    r = await build_asset_report("FIGI", ops, [])
    late = next(p for p in r.purchases if p.price == 120.0)
    early = next(p for p in r.purchases if p.price == 100.0)
    assert late.received_dividends == 0.0
    assert early.received_dividends == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_purchases_sorted_desc_in_output():
    ops = [
        _buy(_dt(2024, 1, 10), 1, 100.0),
        _buy(_dt(2024, 3, 10), 1, 200.0),
        _buy(_dt(2024, 5, 10), 1, 300.0),
    ]
    r = await build_asset_report("FIGI", ops, [])
    dates = [p.date for p in r.purchases]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.asyncio
async def test_future_dividend_counted_only_on_open_lots():
    # Держим 10 акций, объявлен будущий дивиденд 5 ₽/акц => future = 50.
    ops = [_buy(_dt(2024, 1, 10), 10, 100.0)]
    from datetime import date as _date
    r = await build_asset_report(
        "FIGI",
        ops,
        [(_date(2099, 1, 1), 5.0)],
    )
    assert r.future_confirmed == pytest.approx(50.0)
    assert r.total_with_future == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_dividend_split_across_accounts_is_summed():
    # Одна отсечка, но выплата пришла на два счёта разными операциями.
    ops = [
        _buy(_dt(2024, 1, 10), 10, 100.0, acc="A"),
        _buy(_dt(2024, 1, 10), 10, 100.0, acc="B"),
        _div(_dt(2024, 6, 1), 50.0, acc="A"),
        _div(_dt(2024, 6, 1), 50.0, acc="B"),
    ]
    r = await build_asset_report("FIGI", ops, [])
    assert r.total_received == pytest.approx(100.0)
