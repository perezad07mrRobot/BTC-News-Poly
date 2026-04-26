"""Crypto Fear & Greed Index from alternative.me (free, no key)."""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

_URL = "https://api.alternative.me/fng/"


def fetch_fear_greed() -> int | None:
    """Return current F&G value 0–100 (0 = extreme fear, 100 = extreme greed)."""
    try:
        with httpx.Client(timeout=10.0) as c:
            r = c.get(_URL, params={"limit": 1})
            r.raise_for_status()
            data = r.json()
        value = int(data["data"][0]["value"])
        log.info("Fear & Greed Index: %d (%s)", value, data["data"][0].get("value_classification"))
        return value
    except Exception as e:
        log.warning("Fear & Greed fetch failed: %s", e)
        return None
