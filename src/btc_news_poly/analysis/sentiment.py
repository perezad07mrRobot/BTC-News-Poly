"""News headline sentiment via VADER, plus CryptoPanic vote folding."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from math import exp

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from ..data.news_cryptopanic import CryptoPanicPost
from ..data.news_rss import RSSItem

log = logging.getLogger(__name__)

_VADER = SentimentIntensityAnalyzer()


@dataclass
class SentimentResult:
    score: float                # bounded [-1, +1]
    n_items: int
    breakdown: dict[str, float]


def _recency_weight(published: datetime, half_life_hours: float = 6.0) -> float:
    age_h = max(0.0, (datetime.now(tz=timezone.utc) - published).total_seconds() / 3600.0)
    return float(exp(-age_h / half_life_hours))


def _compound(text: str) -> float:
    if not text:
        return 0.0
    return float(_VADER.polarity_scores(text)["compound"])


def analyze(
    rss_items: list[RSSItem],
    cp_posts: list[CryptoPanicPost],
) -> SentimentResult:
    n = 0
    rss_weighted = 0.0
    rss_total_w = 0.0
    for item in rss_items:
        w = _recency_weight(item.published_at)
        s = _compound(item.title)
        rss_weighted += w * s
        rss_total_w += w
        n += 1
    rss_score = rss_weighted / rss_total_w if rss_total_w > 0 else 0.0

    cp_weighted = 0.0
    cp_total_w = 0.0
    cp_vote_score = 0.0
    cp_vote_weight = 0.0
    for post in cp_posts:
        w = _recency_weight(post.published_at)
        s = _compound(post.title)
        cp_weighted += w * s
        cp_total_w += w
        # Bullish/bearish votes — net normalized.
        votes = post.bullish_votes + post.bearish_votes
        if votes > 0:
            net = (post.bullish_votes - post.bearish_votes) / votes
            cp_vote_score += w * net
            cp_vote_weight += w
        n += 1
    cp_text_score = cp_weighted / cp_total_w if cp_total_w > 0 else 0.0
    cp_votes_score = cp_vote_score / cp_vote_weight if cp_vote_weight > 0 else 0.0

    # Combine: text sentiment is primary, votes are secondary.
    combined = 0.45 * rss_score + 0.35 * cp_text_score + 0.20 * cp_votes_score
    combined = max(-1.0, min(1.0, combined))

    return SentimentResult(
        score=combined,
        n_items=n,
        breakdown={
            "rss_text": rss_score,
            "cryptopanic_text": cp_text_score,
            "cryptopanic_votes": cp_votes_score,
        },
    )
