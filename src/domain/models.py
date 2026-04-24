from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(slots=True)
class Purchase:
    """Покупка (лот) с FIFO-учётом частичных продаж."""
    date: datetime
    qty: float
    price: float
    account_id: str
    # Снимки количества акций на дату каждой дивидендной отсечки: date -> qty_at_record_date
    qty_at_record: dict[date, float] = field(default_factory=dict)
    received_dividends: float = 0.0

    @property
    def cost(self) -> float:
        return self.qty * self.price

    @property
    def yield_pct(self) -> float:
        return (self.received_dividends / self.cost * 100.0) if self.cost else 0.0


@dataclass(slots=True)
class DividendEvent:
    """Фактическая выплата дивиденда: record_date + суммарная net-сумма."""
    record_date: date
    pay_date: datetime
    amount: float
    currency: str | None


@dataclass(slots=True)
class Sale:
    date: datetime
    qty: float
    account_id: str


@dataclass(slots=True)
class AssetReport:
    figi: str
    ticker: str
    name: str
    currency: str | None
    total_cost: float
    total_received: float
    total_with_future: float
    future_confirmed: float
    purchases: list[Purchase]  # отсортированы от новых к старым для вывода
