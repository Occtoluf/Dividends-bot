from __future__ import annotations

import logging

from aiogram import Router, html
from aiogram.types import CallbackQuery

from src.bot import formatters, pending_queries
from src.bot.report_service import build_report_for_share
from src.search.normalize import normalize
from src.storage import aliases, cache_instruments
from src.tbank import instruments, operations
from src.tbank.accounts import list_accounts

log = logging.getLogger(__name__)
router = Router(name="alias_pick")


@router.callback_query(lambda c: c.data and c.data.startswith("pick:"))
async def pick(call: CallbackQuery) -> None:
    assert call.data is not None
    _, figi, qhash = call.data.split(":", 2)
    query = pending_queries.get(qhash)

    if query:
        await aliases.upsert(normalize(query), figi)

    share = await cache_instruments.get_by_figi(figi)
    if share is None:
        await call.answer("Инструмент не найден")
        return

    await call.answer(f"Запомнил: {share.ticker}")
    if call.message is None:
        return

    try:
        accounts = await list_accounts()
        await operations.sync_accounts([a.id for a in accounts])
        future = await instruments.get_future_dividends(share.figi)
        report = await build_report_for_share(share.figi, future)
    except Exception as exc:  # noqa: BLE001
        log.exception("Failed to build report for %s", share.ticker)
        await call.message.answer(f"Не удалось собрать отчёт: {html.quote(str(exc))}")
        return

    await call.message.answer(formatters.render_report(report), parse_mode="HTML")
