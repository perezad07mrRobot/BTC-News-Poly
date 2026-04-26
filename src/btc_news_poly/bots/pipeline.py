"""Shared pipeline pieces used by both daily_updown and auto_edge bots."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from ..analysis.sentiment import SentimentResult, analyze
from ..analysis.signal import CombinedSignal, combine
from ..analysis.technical import TAResult, compute as compute_ta
from ..config import Config
from ..data.fear_greed import fetch_fear_greed
from ..data.news_cryptopanic import fetch_posts as fetch_cp_posts
from ..data.news_rss import fetch_rss
from ..data.price import fetch_btc_ohlcv
from ..polymarket.markets import BtcMarket
from ..polymarket.pricing import EdgeDecision, decide_edge, fetch_book_price
from ..polymarket.orders import TradePlan, build_trade_plan
from ..risk import caps as risk_caps

log = logging.getLogger(__name__)


@dataclass
class MarketDataSnapshot:
    ta: TAResult
    sentiment: SentimentResult
    fear_greed: int | None
    signal: CombinedSignal


def collect_market_data(cfg: Config) -> MarketDataSnapshot:
    df = fetch_btc_ohlcv(
        interval=cfg.technical.interval,
        lookback_hours=cfg.technical.lookback_hours,
    )
    ta = compute_ta(
        df,
        rsi_period=cfg.technical.rsi_period,
        ema_short=cfg.technical.ema_short,
        ema_long=cfg.technical.ema_long,
        bb_period=cfg.technical.bb_period,
        bb_std=cfg.technical.bb_std,
        atr_period=cfg.technical.atr_period,
    )
    rss = fetch_rss(cfg.news.rss_feeds, max_age_hours=cfg.news.max_age_hours)
    cp = fetch_cp_posts(
        cfg.secrets.cryptopanic_token,
        currencies=cfg.news.cryptopanic.currencies,
        filter_=cfg.news.cryptopanic.filter,
        limit=cfg.news.cryptopanic.posts_limit,
    )
    sentiment = analyze(rss, cp)
    fg = fetch_fear_greed()
    sig = combine(ta, sentiment, fg, cfg.signal)
    log.info(
        "Signal: prob_up=%.4f raw=%+.3f ta=%+.3f sent=%+.3f fg_score=%+.3f close=%.2f ret24h=%+.2f%%",
        sig.prob_up, sig.raw_score, sig.components["ta"],
        sig.components["sentiment"], sig.components["fear_greed"],
        ta.last_close, ta.return_24h * 100.0,
    )
    return MarketDataSnapshot(ta=ta, sentiment=sentiment, fear_greed=fg, signal=sig)


def edge_for_market(
    cfg: Config, snap: MarketDataSnapshot, market: BtcMarket, side_hint: str = "up"
) -> EdgeDecision | None:
    """Compute edge for a market. side_hint controls which outcome is treated as 'Yes/up'."""
    if len(market.outcomes) != 2:
        log.debug("Skipping non-binary market: %s", market.question)
        return None
    yes = next((o for o in market.outcomes if o.label.lower() in {"yes", "up", "higher"}), market.outcomes[0])
    no = next((o for o in market.outcomes if o.token_id != yes.token_id), market.outcomes[-1])

    yes_book = fetch_book_price(cfg.polymarket.host, yes.token_id)
    no_book = fetch_book_price(cfg.polymarket.host, no.token_id)
    if yes_book is None:
        log.info("No Yes-book for %s — skipping", market.slug)
        return None
    no_mid = no_book.mid if no_book else (1.0 - yes_book.mid)
    return decide_edge(
        prob_up=snap.signal.prob_up,
        yes_mid=yes_book.mid,
        no_mid=no_mid,
        yes_token_id=yes.token_id,
        no_token_id=no.token_id,
    )


def execute_or_dryrun(
    cfg: Config,
    market: BtcMarket,
    decision: EdgeDecision,
    snap: MarketDataSnapshot,
    *,
    dry_run: bool,
    max_usdc_override: float | None,
    available_usdc: float,
) -> dict:
    """Apply caps, build a trade plan, and either submit or log dry-run."""
    plan = build_trade_plan(
        decision,
        cfg=cfg,
        available_usdc=available_usdc,
        extra_notional_cap=max_usdc_override,
    )
    record = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "market_slug": market.slug,
        "market_question": market.question,
        "prob_up": snap.signal.prob_up,
        "components": snap.signal.components,
        "decision": asdict(decision),
        "plan": asdict(plan) if plan else None,
        "dry_run": dry_run,
        "result": None,
        "blocked_reason": None,
    }
    if plan is None:
        record["blocked_reason"] = "no plan (edge or sizing under threshold)"
        _log_record(cfg, record)
        return record

    gate = risk_caps.gate_pre_trade(cfg, plan.notional_usdc, decision.edge)
    if not gate.ok:
        log.warning("Gate blocked trade: %s", gate.reason)
        record["blocked_reason"] = gate.reason
        _log_record(cfg, record)
        return record

    if dry_run:
        log.info("DRY-RUN: would BUY %.2f shares of %s @ %.3f (notional %.2f, edge %.3f)",
                 plan.size_shares, plan.token_id[:10] + "…",
                 plan.price, plan.notional_usdc, plan.edge)
        record["result"] = {"dry_run": True}
        _log_record(cfg, record)
        return record

    # Live submission.
    from ..polymarket.client import build_clob_client
    from ..polymarket.orders import submit_order

    client = build_clob_client(cfg)
    resp = submit_order(client, plan)
    risk_caps.record_trade_notional(cfg, plan.notional_usdc)
    order_id = str(resp.get("orderID") or resp.get("orderId") or resp.get("id") or "unknown")
    risk_caps.add_open_position(cfg, order_id, asdict(plan))
    record["result"] = resp
    _log_record(cfg, record)
    return record


def _log_record(cfg: Config, record: dict) -> None:
    path = cfg.state_dir / "decisions.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def get_available_usdc(cfg: Config, dry_run: bool) -> float:
    """Best-effort USDC balance read; falls back to per-trade cap in dry-run."""
    if dry_run:
        return cfg.risk.per_trade_max_usdc * cfg.risk.max_open_positions
    try:
        from ..polymarket.client import build_clob_client
        client = build_clob_client(cfg)
        bal = client.get_balance_allowance()
        return float(bal.get("balance", 0)) / 1e6
    except Exception as e:
        log.warning("Balance read failed (%s); falling back to per-trade cap", e)
        return cfg.risk.per_trade_max_usdc
