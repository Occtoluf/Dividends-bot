from __future__ import annotations

from datetime import datetime, timedelta, timezone

from t_tech.invest import GetOperationsByCursorRequest, OperationState, OperationType

from src.storage import cursor_store
from src.storage.cursor_store import CachedOperation
from src.tbank.client import money_to_float, services


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
_COUPON_TYPES = {
    OperationType.OPERATION_TYPE_COUPON,
    OperationType.OPERATION_TYPE_BOND_TAX,
    OperationType.OPERATION_TYPE_BOND_TAX_PROGRESSIVE,
    OperationType.OPERATION_TYPE_TAX_CORRECTION_COUPON,
}

_TYPE_LABELS = {
    **{t: "BUY" for t in _BUY_TYPES},
    **{t: "SELL" for t in _SELL_TYPES},
    OperationType.OPERATION_TYPE_DIVIDEND: "DIVIDEND",
    OperationType.OPERATION_TYPE_DIVIDEND_TAX: "DIVIDEND_TAX",
    OperationType.OPERATION_TYPE_DIVIDEND_TRANSFER: "DIVIDEND",
    OperationType.OPERATION_TYPE_COUPON: "COUPON",
    OperationType.OPERATION_TYPE_BOND_TAX: "COUPON_TAX",
    OperationType.OPERATION_TYPE_BOND_TAX_PROGRESSIVE: "COUPON_TAX",
    OperationType.OPERATION_TYPE_TAX_CORRECTION_COUPON: "COUPON_TAX",
}


def _relevant(op_type: OperationType) -> bool:
    return (
        op_type in _BUY_TYPES
        or op_type in _SELL_TYPES
        or op_type in _DIVIDEND_TYPES
        or op_type in _COUPON_TYPES
    )


async def _pull_all(account_id: str, *, force_full: bool = False) -> None:
    """Инкрементный pull операций по счету через GetOperationsByCursor.

    Курсор сохраняем — при следующем вызове продолжаем с места, где остановились.
    Если курсора нет, идём от даты последней сохранённой операции (или 5 лет назад).

    force_full=True — игнорируем курсор и last_cached_date, тянем с 5 лет назад.
    Нужен при добавлении новых типов операций (бэкофилл купонов и т.п.).
    """
    if force_full:
        from_ = datetime.now(timezone.utc) - timedelta(days=365 * 5)
        cursor = ""
    else:
        from_ = await cursor_store.last_cached_date(account_id)
        if from_ is None:
            from_ = datetime.now(timezone.utc) - timedelta(days=365 * 5)
        cursor = await cursor_store.get_cursor(account_id) or ""
    now = datetime.now(timezone.utc)

    async with services() as s:
        while True:
            resp = await s.operations.get_operations_by_cursor(
                GetOperationsByCursorRequest(
                    account_id=account_id,
                    from_=from_,
                    to=now,
                    cursor=cursor,
                    limit=1000,
                    state=OperationState.OPERATION_STATE_EXECUTED,
                )
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
                        price=money_to_float(item.price) if item.price else None,
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


async def sync_accounts(account_ids: list[str], *, force_full: bool = False) -> None:
    for acc_id in account_ids:
        await _pull_all(acc_id, force_full=force_full)


async def load_for_figi(figi: str) -> list[CachedOperation]:
    return await cursor_store.load_for_figi(figi)


async def ensure_coupon_backfill(account_ids: list[str]) -> None:
    """Одноразовый бэкофилл купонных операций для уже синхронизированных аккаунтов.

    До добавления поддержки облигаций COUPON/BOND_TAX отфильтровывались — в БД их нет,
    даже за прошлые периоды. При первом запросе по облигациям делаем полный ресинк.
    Флаг хранится в catalog_meta, чтобы не дёргать ре-синк каждый раз.
    """
    from src.storage.db import connect

    async with connect() as conn:
        cur = await conn.execute(
            "SELECT value FROM catalog_meta WHERE key = ?",
            ("coupon_backfill_done",),
        )
        row = await cur.fetchone()
        if row:
            return

    await sync_accounts(account_ids, force_full=True)

    async with connect() as conn:
        await conn.execute(
            """
            INSERT INTO catalog_meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            ("coupon_backfill_done", datetime.now(timezone.utc).isoformat()),
        )
        await conn.commit()
