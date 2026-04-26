import numpy as np
import pandas as pd

from btc_news_poly.analysis.technical import compute


def _synthetic_ohlcv(prices: np.ndarray) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="1h", tz="UTC")
    high = prices * 1.001
    low = prices * 0.999
    return pd.DataFrame(
        {
            "open": prices,
            "high": high,
            "low": low,
            "close": prices,
            "volume": np.full(len(prices), 100.0),
        },
        index=idx,
    )


def test_uptrend_score_positive():
    prices = np.linspace(40000, 45000, 100)
    df = _synthetic_ohlcv(prices)
    result = compute(df)
    assert result.score > 0
    assert -1.0 <= result.score <= 1.0
    assert result.return_24h > 0


def test_downtrend_score_negative():
    prices = np.linspace(45000, 40000, 100)
    df = _synthetic_ohlcv(prices)
    result = compute(df)
    assert result.score < 0
    assert result.return_24h < 0


def test_flat_score_near_zero():
    prices = np.full(100, 42000.0)
    df = _synthetic_ohlcv(prices)
    result = compute(df)
    assert abs(result.score) < 0.2
