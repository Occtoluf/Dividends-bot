from __future__ import annotations

import logging

from aiogram import Router, html
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.bot import formatters, pending_queries
from src.bot.report_service import build_report_for_bond
from src.search import matcher
from src.storage.cache_bonds import Bond
from src.tbank import instruments, operations
from src.tbank.accounts import list_accounts

log = logging.getLogger(__name__)
router = Router(name="coupons")


@router.message(Command("coupons"))
async def cmd_coupons(message: Message) -> None:
    assert message.text is not None
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Использование: /coupons &lt;тикер или название облигации&gt;")
        return
    query = parts[1].strip()

    await message.chat.do("typing")
    await instruments.refresh_bond_catalog_if_stale()

    result = await matcher.resolve_bond(query)
    if isinstance(result, matcher.BondExact):
        await _send_report(message, result.bond)
        return

    if isinstance(result, matcher.BondSuggestions):
        await _send_suggestions(message, query, [s.bond for s in result.items])
        return

    await message.answer(formatters.render_not_found(query))


async def _send_suggestions(message: Message, query: str, bonds: list[Bond]) -> None:
    h = pending_queries.put(query)
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{b.ticker} — {b.name}",
                callback_data=f"pickb:{b.figi}:{h}",
            )
        ]
        for b in bonds
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(formatters.render_suggestions_prompt(query), reply_markup=kb)


async def _send_report(message: Message, bond: Bond) -> None:
    try:
        accounts = await list_accounts()
        await operations.ensure_coupon_backfill([a.id for a in accounts])
        await operations.sync_accounts([a.id for a in accounts])
        future = await instruments.get_future_coupons(bond.figi)
        report = await build_report_for_bond(bond.figi, future)
    except Exception as exc:  # noqa: BLE001
        log.exception("Failed to build coupon report for %s", bond.ticker)
        await message.answer(f"Не удалось собрать отчёт: {html.quote(str(exc))}")
        return

    await message.answer(formatters.render_report(report), parse_mode="HTML")
