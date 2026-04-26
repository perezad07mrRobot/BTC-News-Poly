"""Combine TA + sentiment + Fear & Greed into prob_up in [0, 1]."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp

from ..config import SignalCfg
from .sentiment import SentimentResult
from .technical import TAResult


@dataclass
class CombinedSignal:
    prob_up: float
    raw_score: float
    components: dict[str, float]


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = exp(-x)
        return 1.0 / (1.0 + z)
    z = exp(x)
    return z / (1.0 + z)


def _fg_score(value: int | None, contrarian: bool) -> float:
    if value is None:
        return 0.0
    # Map 0..100 → -1..+1.
    raw = (value - 50.0) / 50.0
    return -raw if contrarian else raw


def combine(
    ta: TAResult,
    sentiment: SentimentResult,
    fear_greed: int | None,
    cfg: SignalCfg,
) -> CombinedSignal:
    fg_s = _fg_score(fear_greed, cfg.fg_contrarian)
    w = cfg.weights
    raw = (
        w.get("ta", 0.0) * ta.score
        + w.get("sentiment", 0.0) * sentiment.score
        + w.get("fear_greed", 0.0) * fg_s
    )
    prob = _sigmoid(cfg.logit_gain * raw)
    return CombinedSignal(
        prob_up=prob,
        raw_score=raw,
        components={
            "ta": ta.score,
            "sentiment": sentiment.score,
            "fear_greed": fg_s,
        },
    )
