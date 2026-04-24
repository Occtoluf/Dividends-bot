from __future__ import annotations

from datetime import datetime, timezone

from src.storage.db import connect


async def lookup(query_norm: str) -> str | None:
    async with connect() as conn:
        cur = await conn.execute(
            "SELECT figi FROM aliases WHERE query_norm = ?",
            (query_norm,),
        )
        row = await cur.fetchone()
    return row["figi"] if row else None


async def upsert(query_norm: str, figi: str) -> None:
    async with connect() as conn:
        await conn.execute(
            """
            INSERT INTO aliases (query_norm, figi, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(query_norm) DO UPDATE SET
                figi = excluded.figi,
                updated_at = excluded.updated_at
            """,
            (query_norm, figi, datetime.now(timezone.utc).isoformat()),
        )
        await conn.commit()
