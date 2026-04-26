"""Bot 2: scan all active BTC Polymarket markets and trade biggest edge(s)."""

from __future__ import annotations

import logging

from ..config import Config
from ..polymarket.markets import list_btc_markets
from .pipeline import collect_market_data, edge_for_market, execute_or_dryrun, get_available_usdc

log = logging.getLogger(__name__)


def run(cfg: Config, *, dry_run: bool, max_usdc: float | None, top_n: int, min_edge: float) -> int:
    snap = collect_market_data(cfg)
    markets = list_btc_markets(cfg.polymarket.gamma_host, active_only=True)
    if not markets:
        log.warning("No active BTC markets returned by Gamma.")
        return 1

    ranked: list[tuple[float, object, object]] = []
    for m in markets:
        decision = edge_for_market(cfg, snap, m)
        if decision is None:
            continue
        if decision.edge < min_edge:
            continue
        ranked.append((decision.edge, m, decision))

    ranked.sort(key=lambda t: t[0], reverse=True)
    if not ranked:
        log.info("No markets with edge ≥ %.3f", min_edge)
        return 0

    available = get_available_usdc(cfg, dry_run)
    for edge, market, decision in ranked[:top_n]:
        log.info("Edge %.4f on %s", edge, market.question)
        execute_or_dryrun(
            cfg,
            market,
            decision,
            snap,
            dry_run=dry_run,
            max_usdc_override=max_usdc,
            available_usdc=available,
        )
    return 0
