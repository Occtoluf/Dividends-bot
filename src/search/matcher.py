from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from rapidfuzz import fuzz, process

from src.config import settings
from src.search.normalize import normalize, variants
from src.storage import aliases, cache_bonds, cache_instruments
from src.storage.cache_bonds import Bond
from src.storage.cache_instruments import Share


class _Named(Protocol):
    figi: str
    ticker: str
    name: str


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


@dataclass(frozen=True, slots=True)
class BondExact:
    bond: Bond


@dataclass(frozen=True, slots=True)
class BondSuggestion:
    bond: Bond
    score: float


@dataclass(frozen=True, slots=True)
class BondSuggestions:
    items: list[BondSuggestion]


BondMatchResult = BondExact | BondSuggestions | NotFound


def _build_index(items: list) -> dict[str, object]:
    idx: dict[str, object] = {}
    for s in items:
        name_en = getattr(s, "name_en", "") or ""
        for key_src in (s.ticker, s.name, name_en):
            for v in variants(key_src):
                idx.setdefault(v, s)
    return idx


def _fuzzy(q_norm: str, items: list) -> list[tuple[object, float]]:
    if not items:
        return []
    index = _build_index(items)
    matches = process.extract(
        q_norm,
        list(index.keys()),
        scorer=fuzz.WRatio,
        limit=settings.suggestion_limit * 3,
        score_cutoff=settings.fuzzy_score_cutoff,
    )
    seen: dict[str, float] = {}
    ordered: list = []
    for key, score, _ in matches:
        inst = index[key]
        prev = seen.get(inst.figi)
        if prev is None or score > prev:
            seen[inst.figi] = score
            if inst not in ordered:
                ordered.append(inst)
        if len(seen) >= settings.suggestion_limit:
            break
    return [(inst, seen[inst.figi]) for inst in ordered]


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

    hits = _fuzzy(q_norm, await cache_instruments.list_all())
    if not hits:
        return NotFound()
    items = [Suggestion(share=s, score=sc) for s, sc in hits]
    items.sort(key=lambda x: x.score, reverse=True)
    return Suggestions(items=items[: settings.suggestion_limit])


async def resolve_bond(query: str) -> BondMatchResult:
    q_norm = normalize(query)
    if not q_norm:
        return NotFound()

    figi = await aliases.lookup(q_norm)
    if figi:
        bond = await cache_bonds.get_by_figi(figi)
        if bond:
            return BondExact(bond=bond)

    ticker_hit = await cache_bonds.get_by_ticker(q_norm)
    if ticker_hit:
        return BondExact(bond=ticker_hit)

    hits = _fuzzy(q_norm, await cache_bonds.list_all())
    if not hits:
        return NotFound()
    items = [BondSuggestion(bond=b, score=sc) for b, sc in hits]
    items.sort(key=lambda x: x.score, reverse=True)
    return BondSuggestions(items=items[: settings.suggestion_limit])
