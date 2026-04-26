"""Hard risk caps: kill-switch, per-trade max, daily loss limit, open-position count."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..config import Config

log = logging.getLogger(__name__)


@dataclass
class GateResult:
    ok: bool
    reason: str = ""


def _today_key() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def kill_switch_active(cfg: Config) -> bool:
    return Path(cfg.risk.kill_switch_file).exists()


def daily_pnl_path(cfg: Config) -> Path:
    return cfg.state_dir / "daily_pnl.json"


def get_daily_loss(cfg: Config) -> float:
    data = _load_json(daily_pnl_path(cfg))
    return float(data.get(_today_key(), 0.0))


def record_trade_notional(cfg: Config, notional: float) -> None:
    """Track committed notional today; used as proxy for max daily exposure."""
    path = daily_pnl_path(cfg)
    data = _load_json(path)
    key = _today_key()
    data[key] = float(data.get(key, 0.0)) + float(notional)
    _save_json(path, data)


def open_positions_path(cfg: Config) -> Path:
    return cfg.state_dir / "open_positions.json"


def open_position_count(cfg: Config) -> int:
    data = _load_json(open_positions_path(cfg))
    return len(data)


def add_open_position(cfg: Config, order_id: str, plan_dict: dict) -> None:
    path = open_positions_path(cfg)
    data = _load_json(path)
    data[order_id] = plan_dict
    _save_json(path, data)


def gate_pre_trade(cfg: Config, notional_usdc: float, edge: float) -> GateResult:
    """All hard caps in one place. Returns GateResult.ok=False with reason on block."""
    if kill_switch_active(cfg):
        return GateResult(False, f"kill switch present at {cfg.risk.kill_switch_file}")
    if edge < cfg.risk.min_edge:
        return GateResult(False, f"edge {edge:.4f} < min_edge {cfg.risk.min_edge:.4f}")
    if notional_usdc <= 0:
        return GateResult(False, "non-positive notional")
    if notional_usdc > cfg.risk.per_trade_max_usdc:
        return GateResult(
            False,
            f"notional {notional_usdc:.2f} > per_trade_max_usdc {cfg.risk.per_trade_max_usdc:.2f}",
        )
    today_committed = get_daily_loss(cfg)
    if today_committed + notional_usdc > cfg.risk.daily_loss_limit_usdc:
        return GateResult(
            False,
            f"daily exposure {today_committed + notional_usdc:.2f} > "
            f"daily_loss_limit_usdc {cfg.risk.daily_loss_limit_usdc:.2f}",
        )
    if open_position_count(cfg) >= cfg.risk.max_open_positions:
        return GateResult(
            False,
            f"open positions {open_position_count(cfg)} >= max_open_positions {cfg.risk.max_open_positions}",
        )
    return GateResult(True)
