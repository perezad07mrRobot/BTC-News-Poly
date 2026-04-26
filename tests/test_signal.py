from btc_news_poly.analysis.sentiment import SentimentResult
from btc_news_poly.analysis.signal import combine
from btc_news_poly.analysis.technical import TAResult
from btc_news_poly.config import SignalCfg


def _cfg(contrarian: bool = True) -> SignalCfg:
    return SignalCfg(
        weights={"ta": 0.55, "sentiment": 0.30, "fear_greed": 0.15},
        logit_gain=2.5,
        fg_contrarian=contrarian,
    )


def _ta(score: float) -> TAResult:
    return TAResult(
        rsi=50.0, macd_hist=0.0, ema_short=0.0, ema_long=0.0,
        bb_pct_b=0.5, atr=0.0, last_close=0.0, return_24h=0.0,
        score=score, components={},
    )


def _sent(score: float) -> SentimentResult:
    return SentimentResult(score=score, n_items=0, breakdown={})


def test_all_bullish_drives_prob_high():
    sig = combine(_ta(1.0), _sent(1.0), 10, _cfg(contrarian=True))
    assert sig.prob_up > 0.85


def test_all_bearish_drives_prob_low():
    sig = combine(_ta(-1.0), _sent(-1.0), 90, _cfg(contrarian=True))
    assert sig.prob_up < 0.15


def test_neutral_is_half():
    sig = combine(_ta(0.0), _sent(0.0), 50, _cfg(contrarian=True))
    assert abs(sig.prob_up - 0.5) < 1e-6


def test_fg_contrarian_inverts():
    bull_contrarian = combine(_ta(0.0), _sent(0.0), 90, _cfg(contrarian=True)).prob_up
    bull_trend = combine(_ta(0.0), _sent(0.0), 90, _cfg(contrarian=False)).prob_up
    assert bull_contrarian < 0.5 < bull_trend
