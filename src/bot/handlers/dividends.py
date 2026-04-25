from __future__ import annotations

import logging

from aiogram import Router, html
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.bot import formatters, pending_queries
from src.bot.report_service import build_report_for_share
from src.search import matcher
from src.storage.cache_instruments import Share
from src.tbank import instruments, operations
from src.tbank.accounts import list_accounts

log = logging.getLogger(__name__)
router = Router(name="dividends")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Доступные команды:\n"
        "<b>/dividends &lt;тикер&gt;</b> — дивиденды по акции\n"
        "<b>/coupons &lt;тикер&gt;</b> — купоны по облигации\n"
        "<b>/total_dividends</b> — сводка по всем дивидендам\n"
        "<b>/total_coupons</b> — сводка по всем купонам"
    )


@router.message(Command("dividends"))
async def cmd_dividends(message: Message) -> None:
    assert message.text is not None
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Использование: /dividends &lt;тикер или название&gt;")
        return
    query = parts[1].strip()

    await message.chat.do("typing")
    await instruments.refresh_catalog_if_stale()

    result = await matcher.resolve(query)
    if isinstance(result, matcher.Exact):
        await _send_report(message, result.share)
        return

    if isinstance(result, matcher.Suggestions):
        await _send_suggestions(message, query, [s.share for s in result.items])
        return

    await message.answer(formatters.render_not_found(query))


async def _send_suggestions(message: Message, query: str, shares: list[Share]) -> None:
    h = pending_queries.put(query)
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{s.ticker} — {s.name}",
                callback_data=f"pick:{s.figi}:{h}",
            )
        ]
        for s in shares
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(formatters.render_suggestions_prompt(query), reply_markup=kb)


async def _send_report(message: Message, share: Share) -> None:
    try:
        accounts = await list_accounts()
        await operations.sync_accounts([a.id for a in accounts])
        future = await instruments.get_future_dividends(share.figi)
        report = await build_report_for_share(share.figi, future)
    except Exception as exc:  # noqa: BLE001
        log.exception("Failed to build report for %s", share.ticker)
        await message.answer(f"Не удалось собрать отчёт: {html.quote(str(exc))}")
        return

    await message.answer(formatters.render_report(report), parse_mode="HTML")
