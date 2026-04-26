"""CryptoPanic free-tier news ingestion."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

_BASE = "https://cryptopanic.com/api/v1/posts/"


@dataclass
class CryptoPanicPost:
    title: str
    published_at: datetime
    url: str
    bullish_votes: int
    bearish_votes: int
    important_votes: int
    source: str


def fetch_posts(
    token: str | None,
    *,
    currencies: str = "BTC",
    filter_: str = "rising",
    limit: int = 50,
) -> list[CryptoPanicPost]:
    if not token:
        log.info("No CRYPTOPANIC_TOKEN set; skipping CryptoPanic.")
        return []
    params = {
        "auth_token": token,
        "currencies": currencies,
        "filter": filter_,
        "public": "true",
    }
    out: list[CryptoPanicPost] = []
    with httpx.Client(timeout=10.0) as c:
        r = c.get(_BASE, params=params)
        r.raise_for_status()
        data = r.json()
        for item in (data.get("results") or [])[:limit]:
            votes = item.get("votes") or {}
            try:
                published = datetime.fromisoformat(
                    item["published_at"].replace("Z", "+00:00")
                ).astimezone(timezone.utc)
            except Exception:
                published = datetime.now(tz=timezone.utc)
            out.append(
                CryptoPanicPost(
                    title=item.get("title", ""),
                    published_at=published,
                    url=item.get("url", ""),
                    bullish_votes=int(votes.get("positive", 0)),
                    bearish_votes=int(votes.get("negative", 0)),
                    important_votes=int(votes.get("important", 0)),
                    source=(item.get("source") or {}).get("title", "cryptopanic"),
                )
            )
    log.info("CryptoPanic: fetched %d posts", len(out))
    return out
