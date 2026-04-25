from __future__ import annotations

from src.domain.models import AssetReport


_NBSP = " "
_NARROW_NBSP = " "


def _fmt_money(value: float, currency: str | None) -> str:
    sign = "-" if value < 0 else ""
    abs_val = abs(value)
    int_part = f"{int(round(abs_val)):,}".replace(",", _NARROW_NBSP)
    symbol = _currency_symbol(currency)
    return f"{sign}{int_part}{_NBSP}{symbol}"


def _currency_symbol(currency: str | None) -> str:
    if not currency:
        return ""
    c = currency.lower()
    return {"rub": "₽", "usd": "$", "eur": "€", "hkd": "HK$", "cny": "¥"}.get(c, currency.upper())


def _fmt_pct(pct: float) -> str:
    return f"{pct:.1f}%".replace(".", ",")


def render_report(report: AssetReport) -> str:
    lines: list[str] = []
    lines.append(f"<b>{report.name} ({report.ticker})</b>")

    received_pct = (report.total_received / report.total_cost * 100.0) if report.total_cost else 0.0
    future_pct = (report.total_with_future / report.total_cost * 100.0) if report.total_cost else 0.0

    lines.append(
        f"Получено: {_fmt_money(report.total_received, report.currency)} (~{_fmt_pct(received_pct)})"
    )
    if report.future_confirmed > 0:
        lines.append(
            f"С будущим: {_fmt_money(report.total_with_future, report.currency)} (~{_fmt_pct(future_pct)})"
        )

    if report.purchases:
        lines.append("")
        for p in report.purchases:
            date_s = p.date.strftime("%d.%m.%y")
            qty = int(p.qty) if float(p.qty).is_integer() else round(p.qty, 4)
            price_s = _fmt_money(p.price, report.currency)
            div_s = _fmt_money(p.received_dividends, report.currency)
            pct_s = _fmt_pct(p.yield_pct)
            lines.append(f"{date_s} · {qty}×{price_s} · {div_s} (~{pct_s})")
    else:
        lines.append("")
        lines.append("Покупок не найдено.")

    return "\n".join(lines)


def render_suggestions_prompt(query: str) -> str:
    return f"Не нашёл точного совпадения для «{query}». Возможно, вы имели в виду:"


def render_not_found(query: str) -> str:
    return f"Ничего похожего на «{query}» не нашёл."


def render_totals(
    title: str,
    reports: list[AssetReport],
) -> str:
    """Сводный отчёт: сумма received + future по всем инструментам, сгруппировано по валюте."""
    if not reports:
        return f"<b>{title}</b>\nПока нет данных."

    by_currency: dict[str | None, dict[str, float]] = {}
    for r in reports:
        bucket = by_currency.setdefault(r.currency, {"received": 0.0, "future": 0.0})
        bucket["received"] += r.total_received
        bucket["future"] += r.future_confirmed

    lines: list[str] = [f"<b>{title}</b>"]
    for currency, sums in sorted(by_currency.items(), key=lambda kv: (kv[0] or "")):
        received = _fmt_money(sums["received"], currency)
        future = _fmt_money(sums["future"], currency)
        total = _fmt_money(sums["received"] + sums["future"], currency)
        lines.append(f"Получено: {received}")
        if sums["future"] > 0:
            lines.append(f"Будет: +{future}")
            lines.append(f"Итого: {total}")

    nonzero = [r for r in reports if r.total_received > 0 or r.future_confirmed > 0]
    nonzero.sort(key=lambda r: r.total_received + r.future_confirmed, reverse=True)
    if nonzero:
        lines.append("")
        for r in nonzero:
            rec = _fmt_money(r.total_received, r.currency)
            fut = _fmt_money(r.future_confirmed, r.currency)
            if r.future_confirmed > 0:
                lines.append(f"{r.ticker} · {rec} (+{fut})")
            else:
                lines.append(f"{r.ticker} · {rec}")
    return "\n".join(lines)
