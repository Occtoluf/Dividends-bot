from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tinkoff.invest import OperationState, OperationType

from src.storage import cursor_store
from src.storage.cursor_store import CachedOperation
from src.tbank.client import money_to_float, quotation_to_float, services


# Интересующие нас типы операций; всё остальное (комиссии, сервисные) игнорируем.
_BUY_TYPES = {
    OperationType.OPERATION_TYPE_BUY,
    OperationType.OPERATION_TYPE_BUY_CARD,
}
_SELL_TYPES = {
    OperationType.OPERATION_TYPE_SELL,
}
_DIVIDEND_TYPES = {
    OperationType.OPERATION_TYPE_DIVIDEND,
    OperationType.OPERATION_TYPE_DIVIDEND_TAX,
    OperationType.OPERATION_TYPE_DIVIDEND_TRANSFER,
}

_TYPE_LABELS = {
    **{t: "BUY" for t in _BUY_TYPES},
    **{t: "SELL" for t in _SELL_TYPES},
    OperationType.OPERATION_TYPE_DIVIDEND: "DIVIDEND",
    OperationType.OPERATION_TYPE_DIVIDEND_TAX: "DIVIDEND_TAX",
    OperationType.OPERATION_TYPE_DIVIDEND_TRANSFER: "DIVIDEND",
}


def _relevant(op_type: OperationType) -> bool:
    return op_type in _BUY_TYPES or op_type in _SELL_TYPES or op_type in _DIVIDEND_TYPES


async def _pull_all(account_id: str) -> None:
    """Инкрементный pull операций по счету через GetOperationsByCursor.

    Курсор сохраняем — при следующем вызове продолжаем с места, где остановились.
    Если курсора нет, идём от даты последней сохранённой операции (или 5 лет назад).
    """
    from_ = await cursor_store.last_cached_date(account_id)
    if from_ is None:
        from_ = datetime.now(timezone.utc) - timedelta(days=365 * 5)

    cursor = await cursor_store.get_cursor(account_id) or ""
    now = datetime.now(timezone.utc)

    async with services() as s:
        while True:
            resp = await s.operations.get_operations_by_cursor(
                account_id=account_id,
                from_=from_,
                to=now,
                cursor=cursor,
                limit=1000,
                state=OperationState.OPERATION_STATE_EXECUTED,
            )
            batch: list[CachedOperation] = []
            for item in resp.items:
                if not _relevant(item.type):
                    continue
                batch.append(
                    CachedOperation(
                        account_id=account_id,
                        op_id=item.id,
                        figi=item.figi or None,
                        type=_TYPE_LABELS[item.type],
                        date=item.date,
                        qty=float(item.quantity) if item.quantity else None,
                        price=quotation_to_float(item.price) if item.price else None,
                        payment=money_to_float(item.payment) if item.payment else None,
                        currency=getattr(item.payment, "currency", None),
                    )
                )
            await cursor_store.upsert_operations(batch)
            if resp.next_cursor:
                cursor = resp.next_cursor
                await cursor_store.save_cursor(account_id, cursor)
            if not resp.has_next:
                break


async def sync_accounts(account_ids: list[str]) -> None:
    for acc_id in account_ids:
        await _pull_all(acc_id)


async def load_for_figi(figi: str) -> list[CachedOperation]:
    return await cursor_store.load_for_figi(figi)
