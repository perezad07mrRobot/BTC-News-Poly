"""Polymarket Gamma API: discover BTC markets and parse Yes/No outcome tokens."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)


@dataclass
class MarketOutcome:
    label: str             # "Yes" / "No" / "Up" / "Down" / threshold label
    token_id: str          # ERC-1155 token id (string for safety)


@dataclass
class BtcMarket:
    condition_id: str
    question: str
    slug: str
    end_date: datetime | None
    outcomes: list[MarketOutcome]
    raw: dict


_BTC_KEYWORDS = ("bitcoin", "btc")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _decode_field(raw: dict, key: str) -> list:
    val = raw.get(key)
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return []


def _is_btc_market(m: dict) -> bool:
    text = f"{m.get('question', '')} {m.get('slug', '')} {m.get('description', '')}".lower()
    return any(k in text for k in _BTC_KEYWORDS)


def list_btc_markets(
    gamma_host: str = "https://gamma-api.polymarket.com",
    *,
    active_only: bool = True,
    closed: bool = False,
    limit: int = 200,
) -> list[BtcMarket]:
    """Fetch markets from Gamma API and filter to BTC-related, active ones."""
    params = {
        "limit": limit,
        "active": "true" if active_only else "false",
        "closed": "true" if closed else "false",
        "order": "endDate",
        "ascending": "true",
    }
    out: list[BtcMarket] = []
    with httpx.Client(timeout=15.0) as c:
        r = c.get(f"{gamma_host}/markets", params=params)
        r.raise_for_status()
        markets = r.json()

    for m in markets:
        if not _is_btc_market(m):
            continue
        outcomes_labels = _decode_field(m, "outcomes")
        token_ids = _decode_field(m, "clobTokenIds")
        if len(outcomes_labels) != len(token_ids) or not token_ids:
            continue
        outcomes = [
            MarketOutcome(label=str(lbl), token_id=str(tid))
            for lbl, tid in zip(outcomes_labels, token_ids)
        ]
        end = _parse_iso(m.get("endDate") or m.get("end_date_iso"))
        out.append(
            BtcMarket(
                condition_id=str(m.get("conditionId") or m.get("condition_id") or ""),
                question=str(m.get("question") or ""),
                slug=str(m.get("slug") or ""),
                end_date=end,
                outcomes=outcomes,
                raw=m,
            )
        )
    log.info("Gamma: %d BTC markets (active=%s)", len(out), active_only)
    return out


_DAILY_PATTERNS = (
    re.compile(r"\b(up|down)\b.*\bon\b", re.I),
    re.compile(r"\b(up|down)\b.*\btoday\b", re.I),
    re.compile(r"price\b.*\b(up|down)\b", re.I),
    re.compile(r"\bdaily\b.*\b(up|down)\b", re.I),
)


def is_daily_updown(market: BtcMarket) -> bool:
    """Heuristic: identify Polymarket BTC daily up/down markets."""
    q = market.question.lower()
    if "bitcoin" not in q and "btc" not in q:
        return False
    if not any(p.search(q) for p in _DAILY_PATTERNS):
        return False
    labels = {o.label.lower() for o in market.outcomes}
    return ({"up", "down"} <= labels) or ({"yes", "no"} <= labels)


def find_yes_token(market: BtcMarket, side: str = "up") -> MarketOutcome:
    """Return the outcome representing the given directional side."""
    side = side.lower()
    aliases = {
        "up": {"up", "yes", "higher"},
        "down": {"down", "no", "lower"},
    }
    targets = aliases.get(side, {side})
    for o in market.outcomes:
        if o.label.lower() in targets:
            return o
    return market.outcomes[0]
