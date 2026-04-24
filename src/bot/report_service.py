from __future__ import annotations

from src.domain import calculator
from src.domain.models import AssetReport
from src.storage.cache_dividends import ScheduledDividend
from src.tbank import operations


async def build_report_for_share(
    figi: str, future_dividends: list[ScheduledDividend]
) -> AssetReport:
    ops = await operations.load_for_figi(figi)
    future_per_share = [(d.record_date, d.amount_per_share) for d in future_dividends]
    return await calculator.build_asset_report(figi, ops, future_per_share)
