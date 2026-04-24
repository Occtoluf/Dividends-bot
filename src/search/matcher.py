from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

from src.config import settings
from src.search.normalize import normalize, variants
from src.storage import aliases, cache_instruments
from src.storage.cache_instruments import Share


@dataclass(frozen=True, slots=True)
class Exact:
    share: Share


@dataclass(frozen=True, slots=True)
class Suggestion:
    share: Share
    score: float


@dataclass(frozen=True, slots=True)
class Suggestions:
    items: list[Suggestion]


@dataclass(frozen=True, slots=True)
class NotFound:
    pass


MatchResult = Exact | Suggestions | NotFound


def _build_index(shares: list[Share]) -> dict[str, Share]:
    """Ключ нормализованной строки -> Share. Один Share может иметь несколько ключей."""
    idx: dict[str, Share] = {}
    for s in shares:
        for key_src in (s.ticker, s.name, s.name_en or ""):
            for v in variants(key_src):
                idx.setdefault(v, s)
    return idx


async def resolve(query: str) -> MatchResult:
    q_norm = normalize(query)
    if not q_norm:
        return NotFound()

    figi = await aliases.lookup(q_norm)
    if figi:
        share = await cache_instruments.get_by_figi(figi)
        if share:
            return Exact(share=share)

    ticker_hit = await cache_instruments.get_by_ticker(q_norm)
    if ticker_hit:
        return Exact(share=ticker_hit)

    all_shares = await cache_instruments.list_all()
    if not all_shares:
        return NotFound()
    index = _build_index(all_shares)

    matches = process.extract(
        q_norm,
        list(index.keys()),
        scorer=fuzz.WRatio,
        limit=settings.suggestion_limit * 3,
        score_cutoff=settings.fuzzy_score_cutoff,
    )
    seen: dict[str, float] = {}
    ordered: list[Share] = []
    for key, score, _ in matches:
        share = index[key]
        prev = seen.get(share.figi)
        if prev is None or score > prev:
            seen[share.figi] = score
            if share not in ordered:
                ordered.append(share)
        if len(seen) >= settings.suggestion_limit:
            break

    if not ordered:
        return NotFound()

    items = [Suggestion(share=s, score=seen[s.figi]) for s in ordered]
    items.sort(key=lambda x: x.score, reverse=True)
    return Suggestions(items=items[: settings.suggestion_limit])
