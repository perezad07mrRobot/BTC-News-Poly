"""RSS news ingestion (CoinDesk, The Block, Bitcoin Magazine)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

log = logging.getLogger(__name__)


@dataclass
class RSSItem:
    title: str
    summary: str
    published_at: datetime
    url: str
    source: str


def _parse_date(entry: dict) -> datetime:
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            return parsedate_to_datetime(raw).astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.now(tz=timezone.utc)


_BTC_TERMS = ("btc", "bitcoin")


def _is_btc_related(title: str, summary: str) -> bool:
    blob = f"{title} {summary}".lower()
    return any(t in blob for t in _BTC_TERMS)


def fetch_rss(feeds: list[str], max_age_hours: int = 24) -> list[RSSItem]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=max_age_hours)
    out: list[RSSItem] = []
    for url in feeds:
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            log.warning("RSS fetch failed for %s: %s", url, e)
            continue
        source = (parsed.feed or {}).get("title", url)
        for entry in parsed.entries:
            published = _parse_date(entry)
            if published < cutoff:
                continue
            title = entry.get("title", "") or ""
            summary = entry.get("summary", "") or ""
            if not _is_btc_related(title, summary):
                continue
            out.append(
                RSSItem(
                    title=title,
                    summary=summary,
                    published_at=published,
                    url=entry.get("link", ""),
                    source=source,
                )
            )
    log.info("RSS: %d BTC items in last %dh", len(out), max_age_hours)
    return out
