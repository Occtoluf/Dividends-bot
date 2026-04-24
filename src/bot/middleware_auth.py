from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from src.config import settings


class WhitelistMiddleware(BaseMiddleware):
    """Молча игнорирует апдейты от посторонних user_id.

    Мы не отвечаем чужим — меньше поверхности для сканеров. Из логов понятно,
    кто пытался стучаться.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None or user.id != settings.telegram_user_id:
            return None
        return await handler(event, data)
