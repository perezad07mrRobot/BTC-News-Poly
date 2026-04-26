# BTC-News-Poly

24-hour BTC technical analysis + news / sentiment bot that places trades on Polymarket BTC markets.

Two CLI bots share one analysis core:

| Command | Behavior |
| --- | --- |
| `btc-poly daily-updown` | Targets the closest-resolving Polymarket BTC "daily up/down" market. |
| `btc-poly auto-edge`    | Scans every active BTC market and trades the largest model-vs-market edge. |

Both run **one-shot** (analyze → decide → place → exit) and enforce hard risk caps before any live order.

## Pipeline

1. **Price** — 1h BTC OHLCV for the last 7 days (Binance → Coinbase → Kraken fallback).
2. **TA** — RSI, MACD histogram, EMA-20/50 trend, Bollinger %B, ATR-normalized 24h momentum → bounded score in `[-1, +1]`.
3. **News** — CryptoPanic free API + RSS (CoinDesk, The Block, Bitcoin Magazine).
4. **Sentiment** — VADER on headlines + CryptoPanic bullish/bearish votes (recency-weighted).
5. **Macro** — Crypto Fear & Greed Index (alternative.me). Contrarian by default.
6. **Combine** — weighted sum + logistic squash → `prob_up ∈ [0, 1]`.
7. **Polymarket** — Gamma API for market discovery, CLOB book for mid prices.
8. **Edge** — picks the side (Yes / No) with the bigger model-vs-market gap.
9. **Risk caps** — kill-switch file, min-edge gate, per-trade max, daily exposure cap, max open positions.
10. **Order** — fractional-Kelly sizing, GTC limit order via `py-clob-client`.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in POLYMARKET_PK, POLYMARKET_FUNDER, CRYPTOPANIC_TOKEN
```

First run derives Polymarket CLOB API credentials from your wallet key:

```bash
python -m btc_news_poly.polymarket.client
# copy the printed POLYMARKET_API_KEY/SECRET/PASSPHRASE into .env
```

## Usage

```bash
# Always test in dry-run first.
btc-poly daily-updown --dry-run
btc-poly auto-edge    --dry-run --top-n 2 --min-edge 0.05

# Live (still gated by config.yaml hard caps and any state/STOP file).
btc-poly daily-updown --max-usdc 5
btc-poly auto-edge    --top-n 1 --max-usdc 10
```

Suggested cron (UTC):

```
5 0 * * * /path/to/.venv/bin/btc-poly daily-updown --max-usdc 25
0 */6 * * * /path/to/.venv/bin/btc-poly auto-edge --top-n 1 --max-usdc 25
```

## Risk caps (edit `config.yaml`)

| Setting | Default | Meaning |
| --- | --- | --- |
| `per_trade_max_usdc` | 25 | Hard ceiling on single-order notional |
| `daily_loss_limit_usdc` | 50 | Daily committed-notional ceiling (state/daily_pnl.json) |
| `min_edge` | 0.05 | Skip trades with model-vs-market gap below 5pp |
| `max_open_positions` | 3 | Stop opening more if this many exist |
| `kelly_fraction` | 0.25 | Fraction of full Kelly used for sizing |
| `kill_switch_file` | `state/STOP` | If this file exists, all live orders are blocked |

To halt all trading instantly: `touch state/STOP`.

## Project layout

```
src/btc_news_poly/
  cli.py               argparse dispatch
  config.py            YAML + .env → typed Config
  data/                price, news_cryptopanic, news_rss, fear_greed
  analysis/            technical, sentiment, signal (combine)
  polymarket/          client, markets, pricing, orders
  risk/caps.py         hard cap gate
  bots/
    pipeline.py        shared analyze → decide → execute
    daily_updown.py    bot 1 entrypoint
    auto_edge.py       bot 2 entrypoint
tests/                 pytest unit tests
```

## Tests

```bash
.venv/bin/pytest
```

## Disclaimer

This bot trades real money on Polymarket. Use a dedicated wallet, start with `--dry-run`, then use small `--max-usdc` values until you trust the signal in your environment. Past performance of any signal is not predictive of future Polymarket P&L.
