"""BTC OHLCV with public-API fallbacks: Binance → Coinbase → Kraken."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
import pandas as pd

log = logging.getLogger(__name__)

_INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

_BINANCE_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}


def _fetch_binance(interval: str, lookback_hours: int) -> pd.DataFrame:
    if interval not in _BINANCE_INTERVALS:
        raise ValueError(f"Binance unsupported interval {interval!r}")
    end_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    start_ms = end_ms - lookback_hours * 3_600_000
    sec = _INTERVAL_SECONDS[interval]
    limit = min(1000, max(2, lookback_hours * 3600 // sec + 2))
    params = {
        "symbol": "BTCUSDT",
        "interval": interval,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": limit,
    }
    with httpx.Client(timeout=10.0) as c:
        r = c.get("https://api.binance.com/api/v3/klines", params=params)
        r.raise_for_status()
        rows = r.json()
    df = pd.DataFrame(
        rows,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qv", "trades", "tb_base", "tb_quote", "_",
        ],
    )
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.set_index("open_time")[["open", "high", "low", "close", "volume"]]


def _fetch_coinbase(interval: str, lookback_hours: int) -> pd.DataFrame:
    sec = _INTERVAL_SECONDS[interval]
    end = datetime.now(tz=timezone.utc)
    start = end - pd.Timedelta(hours=lookback_hours)
    params = {
        "granularity": sec,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    with httpx.Client(timeout=10.0) as c:
        r = c.get("https://api.exchange.coinbase.com/products/BTC-USD/candles", params=params)
        r.raise_for_status()
        rows = r.json()
    if not rows:
        raise RuntimeError("Coinbase returned no candles")
    # rows are [time, low, high, open, close, volume], newest first.
    df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    df["open_time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.sort_values("open_time").set_index("open_time")
    return df[["open", "high", "low", "close", "volume"]]


def _fetch_kraken(interval: str, lookback_hours: int) -> pd.DataFrame:
    minutes = _INTERVAL_SECONDS[interval] // 60
    if minutes < 1:
        raise ValueError(f"Kraken doesn't support {interval}")
    since = int((datetime.now(tz=timezone.utc).timestamp()) - lookback_hours * 3600)
    params = {"pair": "XBTUSD", "interval": minutes, "since": since}
    with httpx.Client(timeout=10.0) as c:
        r = c.get("https://api.kraken.com/0/public/OHLC", params=params)
        r.raise_for_status()
        body = r.json()
    if body.get("error"):
        raise RuntimeError(f"Kraken error: {body['error']}")
    result = body.get("result") or {}
    pair_key = next((k for k in result.keys() if k != "last"), None)
    if not pair_key:
        raise RuntimeError("Kraken: no OHLC pair in response")
    rows = result[pair_key]
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "vwap", "volume", "count"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col])
    df["open_time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.set_index("open_time")[["open", "high", "low", "close", "volume"]]


_PROVIDERS = (
    ("binance", _fetch_binance),
    ("coinbase", _fetch_coinbase),
    ("kraken", _fetch_kraken),
)


def fetch_btc_ohlcv(interval: str = "1h", lookback_hours: int = 168) -> pd.DataFrame:
    """Try providers in order; return the first that succeeds."""
    last_err: Exception | None = None
    for name, fn in _PROVIDERS:
        try:
            df = fn(interval, lookback_hours)
            if len(df) >= 2:
                log.info("Price source: %s (%d bars)", name, len(df))
                return df
        except Exception as e:
            log.warning("Price provider %s failed: %s", name, e)
            last_err = e
    raise RuntimeError(f"All price providers failed; last error: {last_err}")


def last_24h_return(df: pd.DataFrame) -> float:
    if len(df) < 2:
        return 0.0
    cutoff = df.index[-1] - pd.Timedelta(hours=24)
    window = df.loc[df.index >= cutoff]
    if len(window) < 2:
        window = df.tail(24)
    return float(window["close"].iloc[-1] / window["close"].iloc[0] - 1.0)
