from __future__ import annotations

import re

# Простая транслитерация ru <-> en. Только для fuzzy-поиска, не для отображения.
_RU_TO_EN = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
        "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
)


_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^0-9a-zа-яё]+")


def normalize(text: str) -> str:
    """Канонический ключ: lower, обрезка, только буквы/цифры, схлопнутые пробелы."""
    s = text.strip().lower()
    s = _NON_ALNUM_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def translit(text: str) -> str:
    """ru -> en транслит. Для en-строк безвреден (не меняет)."""
    return text.lower().translate(_RU_TO_EN)


def variants(text: str) -> list[str]:
    """Все строки для fuzzy-поиска: нормализованная + транслит."""
    n = normalize(text)
    if not n:
        return []
    out = {n}
    t = translit(n)
    if t and t != n:
        out.add(t)
    return list(out)
