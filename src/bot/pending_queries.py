from __future__ import annotations

import hashlib
import time

# Короткоживущая in-memory мапа query_hash -> (original_query, expires_at).
# Используется, чтобы не раздуть callback_data (лимит Telegram 64 байта).
# Процессовая память — нам хватает: бот запускается в одном процессе.

_TTL_SECONDS = 10 * 60
_store: dict[str, tuple[str, float]] = {}


def put(query: str) -> str:
    h = hashlib.sha1(query.encode("utf-8")).hexdigest()[:10]
    _store[h] = (query, time.time() + _TTL_SECONDS)
    _gc()
    return h


def get(h: str) -> str | None:
    item = _store.get(h)
    if not item:
        return None
    query, exp = item
    if time.time() > exp:
        _store.pop(h, None)
        return None
    return query


def _gc() -> None:
    if len(_store) < 256:
        return
    now = time.time()
    for k in [k for k, (_, exp) in _store.items() if exp < now]:
        _store.pop(k, None)
