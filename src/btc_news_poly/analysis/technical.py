"""Technical indicators → bounded score in [-1, +1]."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class TAResult:
    rsi: float
    macd_hist: float
    ema_short: float
    ema_long: float
    bb_pct_b: float
    atr: float
    last_close: float
    return_24h: float
    score: float       # bounded [-1, +1]
    components: dict[str, float]


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return rsi.fillna(50.0)


def _macd_hist(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    macd = _ema(close, fast) - _ema(close, slow)
    sig = _ema(macd, signal)
    return macd - sig


def _bb_pct_b(close: pd.Series, period: int, k: float) -> pd.Series:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    upper = mid + k * std
    lower = mid - k * std
    width = (upper - lower).replace(0, np.nan)
    pct_b = (close - lower) / width
    return pct_b.fillna(0.5)


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    if not np.isfinite(x):
        return 0.0
    return float(max(lo, min(hi, x)))


def compute(
    df: pd.DataFrame,
    *,
    rsi_period: int = 14,
    ema_short: int = 20,
    ema_long: int = 50,
    bb_period: int = 20,
    bb_std: float = 2.0,
    atr_period: int = 14,
) -> TAResult:
    """Compute indicators and a bounded directional score from OHLCV."""
    if len(df) < max(ema_long, bb_period, rsi_period) + 5:
        raise ValueError(f"Not enough rows for TA: {len(df)}")

    close = df["close"]
    rsi = _rsi(close, rsi_period).iloc[-1]
    macd_hist = _macd_hist(close).iloc[-1]
    e_short = _ema(close, ema_short).iloc[-1]
    e_long = _ema(close, ema_long).iloc[-1]
    pct_b = _bb_pct_b(close, bb_period, bb_std).iloc[-1]
    atr = _atr(df, atr_period).iloc[-1]
    last = float(close.iloc[-1])

    cutoff = df.index[-1] - pd.Timedelta(hours=24)
    win = df.loc[df.index >= cutoff]
    if len(win) < 2:
        win = df.tail(24)
    ret_24h = float(win["close"].iloc[-1] / win["close"].iloc[0] - 1.0)

    # Component scores in [-1, +1].
    # RSI: mean-reverting around 50. >70 overbought (mildly bearish), <30 oversold (mildly bullish).
    rsi_score = _clip((50.0 - float(rsi)) / 30.0)
    # MACD histogram: trend signal, normalize by ATR-ish scale.
    macd_score = _clip(float(macd_hist) / max(float(atr), 1e-9) * 0.5)
    # Trend: short EMA vs long EMA, normalized by long EMA.
    trend_score = _clip((float(e_short) - float(e_long)) / max(float(e_long), 1e-9) * 50.0)
    # %B: 0.5 neutral; >1 overbought, <0 oversold. Counter-trend mild signal.
    bb_score = _clip((0.5 - float(pct_b)) * 2.0)
    # 24h momentum: scaled by ATR/price for vol normalization.
    vol_norm = max(float(atr) / max(last, 1e-9), 1e-4)
    mom_score = _clip(ret_24h / (3.0 * vol_norm))

    components = {
        "rsi": rsi_score,
        "macd": macd_score,
        "trend": trend_score,
        "bbands": bb_score,
        "momentum_24h": mom_score,
    }
    # Weighted blend — momentum + trend dominate, mean-reversion as tilt.
    score = _clip(
        0.35 * mom_score
        + 0.30 * trend_score
        + 0.20 * macd_score
        + 0.10 * rsi_score
        + 0.05 * bb_score
    )

    return TAResult(
        rsi=float(rsi),
        macd_hist=float(macd_hist),
        ema_short=float(e_short),
        ema_long=float(e_long),
        bb_pct_b=float(pct_b),
        atr=float(atr),
        last_close=last,
        return_24h=ret_24h,
        score=score,
        components=components,
    )
