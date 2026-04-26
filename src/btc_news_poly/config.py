from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass
class SignalCfg:
    weights: dict[str, float]
    logit_gain: float
    fg_contrarian: bool


@dataclass
class TechnicalCfg:
    interval: str
    lookback_hours: int
    rsi_period: int
    ema_short: int
    ema_long: int
    bb_period: int
    bb_std: float
    atr_period: int


@dataclass
class CryptoPanicCfg:
    filter: str
    currencies: str
    posts_limit: int


@dataclass
class NewsCfg:
    cryptopanic: CryptoPanicCfg
    rss_feeds: list[str]
    max_age_hours: int


@dataclass
class RiskCfg:
    per_trade_max_usdc: float
    daily_loss_limit_usdc: float
    min_edge: float
    max_open_positions: int
    kelly_fraction: float
    state_dir: str
    kill_switch_file: str


@dataclass
class PolymarketCfg:
    host: str
    gamma_host: str
    chain_id: int
    price_offset_from_mid: float
    tick_size: float


@dataclass
class Secrets:
    polymarket_pk: str | None = None
    polymarket_funder: str | None = None
    polymarket_api_key: str | None = None
    polymarket_api_secret: str | None = None
    polymarket_api_passphrase: str | None = None
    cryptopanic_token: str | None = None


@dataclass
class Config:
    signal: SignalCfg
    technical: TechnicalCfg
    news: NewsCfg
    risk: RiskCfg
    polymarket: PolymarketCfg
    secrets: Secrets = field(default_factory=Secrets)

    @property
    def state_dir(self) -> Path:
        p = Path(self.risk.state_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(path: str | Path = "config.yaml") -> Config:
    load_dotenv(override=False)
    raw = _load_yaml(Path(path))

    signal = SignalCfg(**raw["signal"])
    technical = TechnicalCfg(**raw["technical"])
    news_raw = raw["news"]
    news = NewsCfg(
        cryptopanic=CryptoPanicCfg(**news_raw["cryptopanic"]),
        rss_feeds=list(news_raw["rss_feeds"]),
        max_age_hours=int(news_raw["max_age_hours"]),
    )
    risk = RiskCfg(**raw["risk"])
    polymarket = PolymarketCfg(**raw["polymarket"])

    secrets = Secrets(
        polymarket_pk=os.getenv("POLYMARKET_PK"),
        polymarket_funder=os.getenv("POLYMARKET_FUNDER"),
        polymarket_api_key=os.getenv("POLYMARKET_API_KEY"),
        polymarket_api_secret=os.getenv("POLYMARKET_API_SECRET"),
        polymarket_api_passphrase=os.getenv("POLYMARKET_API_PASSPHRASE"),
        cryptopanic_token=os.getenv("CRYPTOPANIC_TOKEN"),
    )
    if os.getenv("POLYMARKET_HOST"):
        polymarket.host = os.environ["POLYMARKET_HOST"]
    if os.getenv("POLYMARKET_CHAIN_ID"):
        polymarket.chain_id = int(os.environ["POLYMARKET_CHAIN_ID"])

    return Config(
        signal=signal,
        technical=technical,
        news=news,
        risk=risk,
        polymarket=polymarket,
        secrets=secrets,
    )
