"""Thin wrapper around py-clob-client. Imports lazily so dry-run works without the SDK."""

from __future__ import annotations

import logging
from typing import Any

from ..config import Config

log = logging.getLogger(__name__)


def build_clob_client(cfg: Config) -> Any:
    """Build an authenticated CLOB client. Raises if required secrets are missing."""
    sec = cfg.secrets
    if not sec.polymarket_pk:
        raise RuntimeError("POLYMARKET_PK is required for live mode.")
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
    except ImportError as e:
        raise RuntimeError(
            "py-clob-client not installed. `pip install py-clob-client` or use --dry-run."
        ) from e

    creds = None
    if sec.polymarket_api_key and sec.polymarket_api_secret and sec.polymarket_api_passphrase:
        creds = ApiCreds(
            api_key=sec.polymarket_api_key,
            api_secret=sec.polymarket_api_secret,
            api_passphrase=sec.polymarket_api_passphrase,
        )

    client = ClobClient(
        host=cfg.polymarket.host,
        chain_id=cfg.polymarket.chain_id,
        key=sec.polymarket_pk,
        creds=creds,
        funder=sec.polymarket_funder,
        signature_type=2 if sec.polymarket_funder else 0,
    )

    if creds is None:
        log.info("Deriving CLOB API credentials (one-time per wallet)...")
        derived = client.create_or_derive_api_creds()
        client.set_api_creds(derived)
        log.warning(
            "Save these credentials to .env to skip derivation next run:\n"
            "  POLYMARKET_API_KEY=%s\n"
            "  POLYMARKET_API_SECRET=%s\n"
            "  POLYMARKET_API_PASSPHRASE=%s",
            derived.api_key, derived.api_secret, derived.api_passphrase,
        )
    return client


def derive_creds_cli() -> None:
    """Convenience: `python -m btc_news_poly.polymarket.client` to print creds."""
    from ..config import load_config
    from ..logging_setup import setup_logging

    setup_logging("INFO")
    cfg = load_config()
    build_clob_client(cfg)


if __name__ == "__main__":
    derive_creds_cli()
