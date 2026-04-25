from __future__ import annotations

import logging

from aiogram import Router, html
from aiogram.filters import Command
from aiogram.types import Message

from src.bot import formatters
from src.bot.report_service import build_report_for_bond, build_report_for_share
from src.domain.models import AssetReport
from src.storage.cursor_store import list_figis_with_income
from src.tbank import instruments, operations
from src.tbank.accounts import list_accounts

log = logging.getLogger(__name__)
router = Router(name="totals")


async def _build_totals(income_type: str) -> list[AssetReport]:
    figis = await list_figis_with_income(income_type)
    reports: list[AssetReport] = []
    for figi in figis:
        try:
            if income_type == "DIVIDEND":
                future = await instruments.get_future_dividends(figi)
                report = await build_report_for_share(figi, future)
            else:
                future = await instruments.get_future_coupons(figi)
                report = await build_report_for_bond(figi, future)
            reports.append(report)
        except Exception:  # noqa: BLE001
            log.exception("Totals: failed to build report for %s", figi)
    return reports


@router.message(Command("total_dividends"))
async def cmd_total_dividends(message: Message) -> None:
    await message.chat.do("typing")
    try:
        accounts = await list_accounts()
        await operations.sync_accounts([a.id for a in accounts])
        await instruments.refresh_catalog_if_stale()
        reports = await _build_totals("DIVIDEND")
    except Exception as exc:  # noqa: BLE001
        log.exception("Failed to build totals for dividends")
        await message.answer(f"Не удалось собрать сводку: {html.quote(str(exc))}")
        return
    await message.answer(
        formatters.render_totals("Дивиденды — всего", reports), parse_mode="HTML"
    )


@router.message(Command("total_coupons"))
async def cmd_total_coupons(message: Message) -> None:
    await message.chat.do("typing")
    try:
        accounts = await list_accounts()
        await operations.ensure_coupon_backfill([a.id for a in accounts])
        await operations.sync_accounts([a.id for a in accounts])
        await instruments.refresh_bond_catalog_if_stale()
        reports = await _build_totals("COUPON")
    except Exception as exc:  # noqa: BLE001
        log.exception("Failed to build totals for coupons")
        await message.answer(f"Не удалось собрать сводку: {html.quote(str(exc))}")
        return
    await message.answer(
        formatters.render_totals("Купоны — всего", reports), parse_mode="HTML"
    )
