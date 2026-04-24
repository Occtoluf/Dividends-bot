from __future__ import annotations

from dataclasses import dataclass

from tinkoff.invest import AccountStatus, AccountType

from src.tbank.client import services


@dataclass(frozen=True, slots=True)
class Account:
    id: str
    name: str
    type: str  # "broker" | "iis" | "other"


def _account_type_label(t: AccountType) -> str:
    if t == AccountType.ACCOUNT_TYPE_TINKOFF:
        return "broker"
    if t == AccountType.ACCOUNT_TYPE_TINKOFF_IIS:
        return "iis"
    return "other"


async def list_accounts() -> list[Account]:
    """Возвращает активные счета пользователя: обычно БС + ИИС."""
    async with services() as s:
        resp = await s.users.get_accounts()
    result: list[Account] = []
    for acc in resp.accounts:
        if acc.status != AccountStatus.ACCOUNT_STATUS_OPEN:
            continue
        result.append(
            Account(
                id=acc.id,
                name=acc.name,
                type=_account_type_label(acc.type),
            )
        )
    return result
