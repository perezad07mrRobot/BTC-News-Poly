"""Bot 1: target Polymarket BTC 'will price be up today?' style market."""

from __future__ import annotations

import logging

from ..config import Config
from ..polymarket.markets import is_daily_updown, list_btc_markets
from .pipeline import collect_market_data, edge_for_market, execute_or_dryrun, get_available_usdc

log = logging.getLogger(__name__)


def run(cfg: Config, *, dry_run: bool, max_usdc: float | None) -> int:
    snap = collect_market_data(cfg)

    markets = list_btc_markets(cfg.polymarket.gamma_host, active_only=True)
    candidates = [m for m in markets if is_daily_updown(m)]
    if not candidates:
        log.warning("No active BTC daily up/down market found.")
        return 1

    from datetime import datetime, timezone
    far_future = datetime(9999, 1, 1, tzinfo=timezone.utc)
    candidates.sort(key=lambda m: m.end_date or far_future)
    target = candidates[0]
    log.info("Target market: %s (ends %s)", target.question, target.end_date)

    decision = edge_for_market(cfg, snap, target)
    if decision is None:
        log.warning("Could not compute edge for target market.")
        return 1

    available = get_available_usdc(cfg, dry_run)
    execute_or_dryrun(
        cfg,
        target,
        decision,
        snap,
        dry_run=dry_run,
        max_usdc_override=max_usdc,
        available_usdc=available,
    )
    return 0
