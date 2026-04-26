"""CLI entrypoint: `btc-poly daily-updown ...` / `btc-poly auto-edge ...`."""

from __future__ import annotations

import argparse
import sys

from .bots import auto_edge, daily_updown
from .config import load_config
from .logging_setup import setup_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="btc-poly")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_daily = sub.add_parser("daily-updown", help="Trade BTC daily up/down market")
    p_daily.add_argument("--dry-run", action="store_true", help="Plan only, no live order")
    p_daily.add_argument("--max-usdc", type=float, default=None,
                         help="Optional per-run cap (must be ≤ per_trade_max_usdc)")

    p_auto = sub.add_parser("auto-edge", help="Scan all BTC markets, trade biggest edge")
    p_auto.add_argument("--dry-run", action="store_true")
    p_auto.add_argument("--top-n", type=int, default=1, help="Trade top-N edges")
    p_auto.add_argument("--min-edge", type=float, default=None,
                        help="Override config min_edge for this run")
    p_auto.add_argument("--max-usdc", type=float, default=None)

    args = parser.parse_args(argv)
    setup_logging(args.log_level)
    cfg = load_config(args.config)

    if args.cmd == "daily-updown":
        return daily_updown.run(cfg, dry_run=args.dry_run, max_usdc=args.max_usdc)
    if args.cmd == "auto-edge":
        min_edge = args.min_edge if args.min_edge is not None else cfg.risk.min_edge
        return auto_edge.run(
            cfg,
            dry_run=args.dry_run,
            max_usdc=args.max_usdc,
            top_n=args.top_n,
            min_edge=min_edge,
        )
    parser.error(f"Unknown command {args.cmd!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
