from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.bot.handlers import build_router
from src.bot.middleware_auth import WhitelistMiddleware
from src.config import settings
from src.storage.db import init as init_db


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    log = logging.getLogger("bot")

    await init_db()

    bot = Bot(
        token=settings.telegram_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    wl = WhitelistMiddleware()
    dp.message.middleware(wl)
    dp.callback_query.middleware(wl)
    dp.include_router(build_router())

    log.info("Bot started. Whitelisted user_id=%s", settings.telegram_user_id)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())
