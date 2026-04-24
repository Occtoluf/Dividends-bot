from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from t_tech.invest import AsyncClient
from t_tech.invest.services import AsyncServices

from src.config import settings


@asynccontextmanager
async def services() -> AsyncIterator[AsyncServices]:
    """Создаёт async gRPC-клиент T-Invest на время блока.

    Мы не держим один глобальный клиент между запросами — gRPC-канал дешёвый,
    а жизненный цикл на команду изолирует ошибки и не плодит сессий.
    """
    async with AsyncClient(settings.tbank_token) as client:
        yield client


def quotation_to_float(q) -> float:
    if q is None:
        return 0.0
    return float(q.units) + float(q.nano) / 1_000_000_000


def money_to_float(m) -> float:
    if m is None:
        return 0.0
    return float(m.units) + float(m.nano) / 1_000_000_000


def money_currency(m) -> str | None:
    if m is None:
        return None
    return getattr(m, "currency", None)
