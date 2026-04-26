from btc_news_poly.config import (
    Config,
    CryptoPanicCfg,
    NewsCfg,
    PolymarketCfg,
    RiskCfg,
    Secrets,
    SignalCfg,
    TechnicalCfg,
)
from btc_news_poly.polymarket.orders import build_trade_plan
from btc_news_poly.polymarket.pricing import EdgeDecision, decide_edge


def _cfg() -> Config:
    return Config(
        signal=SignalCfg(weights={"ta": 0.55, "sentiment": 0.30, "fear_greed": 0.15},
                         logit_gain=2.5, fg_contrarian=True),
        technical=TechnicalCfg(interval="1h", lookback_hours=168, rsi_period=14,
                               ema_short=20, ema_long=50, bb_period=20, bb_std=2.0,
                               atr_period=14),
        news=NewsCfg(
            cryptopanic=CryptoPanicCfg(filter="rising", currencies="BTC", posts_limit=50),
            rss_feeds=[], max_age_hours=24,
        ),
        risk=RiskCfg(
            per_trade_max_usdc=25.0,
            daily_loss_limit_usdc=50.0,
            min_edge=0.05,
            max_open_positions=3,
            kelly_fraction=0.25,
            state_dir="state-test",
            kill_switch_file="state-test/STOP",
        ),
        polymarket=PolymarketCfg(
            host="x", gamma_host="x", chain_id=137,
            price_offset_from_mid=0.01, tick_size=0.01,
        ),
        secrets=Secrets(),
    )


def test_decide_edge_picks_yes_when_model_higher():
    d = decide_edge(prob_up=0.70, yes_mid=0.55, no_mid=0.45,
                    yes_token_id="Y", no_token_id="N")
    assert d.side == "BUY_YES"
    assert d.token_id == "Y"
    assert d.edge > 0.10


def test_decide_edge_picks_no_when_model_lower():
    d = decide_edge(prob_up=0.30, yes_mid=0.55, no_mid=0.45,
                    yes_token_id="Y", no_token_id="N")
    assert d.side == "BUY_NO"
    assert d.token_id == "N"


def test_plan_respects_per_trade_cap():
    cfg = _cfg()
    decision = EdgeDecision(
        side="BUY_YES", token_id="Y", yes_token_id="Y", no_token_id="N",
        model_prob_up=0.80, yes_mid=0.50, no_mid=0.50,
        edge=0.30, chosen_prob=0.80, chosen_mid=0.50,
    )
    plan = build_trade_plan(decision, cfg=cfg, available_usdc=10_000.0)
    assert plan is not None
    assert plan.notional_usdc <= cfg.risk.per_trade_max_usdc + 1e-6
    assert 0.0 < plan.price < 1.0
    assert plan.size_shares > 0


def test_plan_skips_when_edge_too_small():
    cfg = _cfg()
    decision = EdgeDecision(
        side="BUY_YES", token_id="Y", yes_token_id="Y", no_token_id="N",
        model_prob_up=0.51, yes_mid=0.50, no_mid=0.50,
        edge=0.01, chosen_prob=0.51, chosen_mid=0.50,
    )
    plan = build_trade_plan(decision, cfg=cfg, available_usdc=1000.0)
    assert plan is None
