from pathlib import Path

import pytest

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
from btc_news_poly.risk import caps


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    state_dir = tmp_path / "state"
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
            state_dir=str(state_dir),
            kill_switch_file=str(state_dir / "STOP"),
        ),
        polymarket=PolymarketCfg(
            host="x", gamma_host="x", chain_id=137,
            price_offset_from_mid=0.01, tick_size=0.01,
        ),
        secrets=Secrets(),
    )


def test_min_edge_blocks(cfg):
    r = caps.gate_pre_trade(cfg, notional_usdc=10.0, edge=0.01)
    assert not r.ok
    assert "edge" in r.reason


def test_per_trade_max_blocks(cfg):
    r = caps.gate_pre_trade(cfg, notional_usdc=100.0, edge=0.10)
    assert not r.ok
    assert "per_trade_max_usdc" in r.reason


def test_kill_switch_blocks(cfg):
    Path(cfg.risk.kill_switch_file).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.risk.kill_switch_file).write_text("stop")
    r = caps.gate_pre_trade(cfg, notional_usdc=10.0, edge=0.10)
    assert not r.ok
    assert "kill" in r.reason.lower()


def test_daily_limit_blocks(cfg):
    caps.record_trade_notional(cfg, 45.0)
    r = caps.gate_pre_trade(cfg, notional_usdc=10.0, edge=0.10)
    assert not r.ok
    assert "daily" in r.reason.lower()


def test_happy_path(cfg):
    r = caps.gate_pre_trade(cfg, notional_usdc=20.0, edge=0.10)
    assert r.ok, r.reason
