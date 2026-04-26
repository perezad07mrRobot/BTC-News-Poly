"""Order-book mid pricing and edge calculation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)


@dataclass
class BookPrice:
    best_bid: float
    best_ask: float
    mid: float


def fetch_book_price(host: str, token_id: str) -> BookPrice | None:
    """Fetch best bid/ask via the public CLOB book endpoint (no auth required)."""
    try:
        with httpx.Client(timeout=10.0) as c:
            r = c.get(f"{host}/book", params={"token_id": token_id})
            r.raise_for_status()
            book = r.json()
    except Exception as e:
        log.warning("Order book fetch failed for %s: %s", token_id, e)
        return None

    bids = book.get("bids") or []
    asks = book.get("asks") or []
    if not bids or not asks:
        return None
    best_bid = float(bids[0]["price"])
    best_ask = float(asks[0]["price"])
    if best_ask <= best_bid:
        return None
    mid = (best_bid + best_ask) / 2.0
    return BookPrice(best_bid=best_bid, best_ask=best_ask, mid=mid)


@dataclass
class EdgeDecision:
    side: str               # "BUY" Yes or "BUY" No
    token_id: str
    yes_token_id: str
    no_token_id: str
    model_prob_up: float
    yes_mid: float
    no_mid: float
    edge: float             # signed: positive = trade is worth taking
    chosen_prob: float      # model prob for the chosen side
    chosen_mid: float


def decide_edge(
    *,
    prob_up: float,
    yes_mid: float,
    no_mid: float | None,
    yes_token_id: str,
    no_token_id: str,
) -> EdgeDecision:
    """Pick the side with the bigger model-vs-market gap."""
    if no_mid is None:
        no_mid = 1.0 - yes_mid
    edge_yes = prob_up - yes_mid
    edge_no = (1.0 - prob_up) - no_mid
    if edge_yes >= edge_no:
        return EdgeDecision(
            side="BUY_YES",
            token_id=yes_token_id,
            yes_token_id=yes_token_id,
            no_token_id=no_token_id,
            model_prob_up=prob_up,
            yes_mid=yes_mid,
            no_mid=no_mid,
            edge=edge_yes,
            chosen_prob=prob_up,
            chosen_mid=yes_mid,
        )
    return EdgeDecision(
        side="BUY_NO",
        token_id=no_token_id,
        yes_token_id=yes_token_id,
        no_token_id=no_token_id,
        model_prob_up=prob_up,
        yes_mid=yes_mid,
        no_mid=no_mid,
        edge=edge_no,
        chosen_prob=1.0 - prob_up,
        chosen_mid=no_mid,
    )
