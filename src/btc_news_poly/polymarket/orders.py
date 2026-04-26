"""Order construction & submission with hard cap enforcement."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from ..config import Config
from .pricing import EdgeDecision

log = logging.getLogger(__name__)


@dataclass
class TradePlan:
    token_id: str
    side: str               # "BUY"
    price: float            # limit price for the chosen Yes/No share
    size_shares: float      # # of shares to buy
    notional_usdc: float    # price * size
    edge: float
    rationale: str


def _round_tick(price: float, tick: float) -> float:
    return round(round(price / tick) * tick, 4)


def build_trade_plan(
    decision: EdgeDecision,
    *,
    cfg: Config,
    available_usdc: float,
    extra_notional_cap: float | None = None,
) -> TradePlan | None:
    """Translate an edge decision into a concrete cap-enforced limit order plan."""
    risk = cfg.risk
    if decision.edge < risk.min_edge:
        log.info(
            "Skip: edge %.4f below min_edge %.4f", decision.edge, risk.min_edge
        )
        return None

    # Kelly fraction sizing for binary outcomes:
    #   f* = (p * (1 - price) - (1 - p) * price) / (1 - price)
    p = max(0.001, min(0.999, decision.chosen_prob))
    price_mid = max(0.01, min(0.99, decision.chosen_mid))
    kelly_full = (p * (1 - price_mid) - (1 - p) * price_mid) / (1 - price_mid)
    kelly_fraction = max(0.0, kelly_full * risk.kelly_fraction)

    # Notional bankroll = min(available USDC, per_trade_max).
    bankroll = min(available_usdc, risk.per_trade_max_usdc)
    if extra_notional_cap is not None:
        bankroll = min(bankroll, extra_notional_cap)
    notional = min(risk.per_trade_max_usdc, bankroll * kelly_fraction)
    if notional < 1.0:
        log.info("Skip: notional %.2f USDC under $1 minimum", notional)
        return None

    # Place limit slightly worse than mid for a quicker fill.
    limit_price = _round_tick(
        min(0.99, price_mid + cfg.polymarket.price_offset_from_mid),
        cfg.polymarket.tick_size,
    )
    size_shares = round(notional / limit_price, 2)

    rationale = (
        f"prob={p:.3f} mid={price_mid:.3f} edge={decision.edge:.3f} "
        f"kelly_full={kelly_full:.3f} kelly_used={kelly_fraction:.3f}"
    )
    return TradePlan(
        token_id=decision.token_id,
        side="BUY",
        price=limit_price,
        size_shares=size_shares,
        notional_usdc=round(size_shares * limit_price, 4),
        edge=decision.edge,
        rationale=rationale,
    )


def submit_order(client: Any, plan: TradePlan) -> dict:
    """Submit a GTC limit BUY via py-clob-client. Returns the response dict."""
    from py_clob_client.clob_types import OrderArgs, OrderType  # type: ignore
    from py_clob_client.order_builder.constants import BUY  # type: ignore

    args = OrderArgs(
        price=plan.price,
        size=plan.size_shares,
        side=BUY,
        token_id=plan.token_id,
    )
    signed = client.create_order(args)
    resp = client.post_order(signed, OrderType.GTC)
    log.info("Order submitted: %s plan=%s", resp, asdict(plan))
    return resp
