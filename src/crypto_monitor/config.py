from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class StrategyConfig:
    ema_fast: int = 20
    ema_slow: int = 50
    ema_min_separation_pct: float = 0.02
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    atr_stop_multiple: float = 1.5
    signal_threshold: int = 4
    strong_signal_threshold: int = 5
    minimum_cvd_ratio: float = 0.03
    minimum_oi_change_pct: float = 0.10
    volume_spike_ratio: float = 1.20
    max_abs_funding_rate: float = 0.0008
    pivot_left_bars: int = 3
    pivot_right_bars: int = 2
    divergence_min_separation_bars: int = 5
    divergence_max_separation_bars: int = 40
    divergence_min_price_atr: float = 0.1
    divergence_min_macd_difference: float = 0.0
    divergence_expiry_bars: int = 3
    divergence_stop_atr_buffer: float = 0.2
    risk_reward_ratio: float = 1.0


@dataclass(frozen=True)
class RiskConfig:
    account_equity_usdt: float = 0.0
    risk_per_trade_pct: float = 1.0
    fee_rate_pct: float = 0.05
    slippage_pct: float = 0.02
    minimum_cost_adjusted_rr: float = 0.5
    max_stop_distance_pct: float = 5.0


@dataclass(frozen=True)
class AppConfig:
    symbols: tuple[str, ...]
    timeframe: str
    scan_interval_seconds: int
    cvd_window_minutes: int
    cvd_stale_after_seconds: int
    alert_cooldown_minutes: int
    confirmation_scans: int
    signal_log_path: str
    telegram_bot_token: str
    telegram_chat_id: str
    strategy: StrategyConfig
    risk: RiskConfig


def _mapping(value: Any, key: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{key} 必須是 YAML 物件")
    return value


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path or os.getenv("CONFIG_PATH", "config.yaml"))
    if not config_path.exists():
        raise FileNotFoundError(
            f"找不到 {config_path}；請先複製 config.example.yaml 為 config.yaml"
        )
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    strategy = StrategyConfig(**_mapping(raw.get("strategy"), "strategy"))
    risk = RiskConfig(**_mapping(raw.get("risk"), "risk"))
    symbols = tuple(raw.get("symbols") or ())
    if not symbols:
        raise ValueError("symbols 至少要設定一個 OKX 永續合約")
    if any(not symbol.endswith("-SWAP") for symbol in symbols):
        raise ValueError("第一版 symbols 只接受 OKX 的 *-SWAP 永續合約")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if strategy.ema_fast >= strategy.ema_slow:
        raise ValueError("ema_fast 必須小於 ema_slow")
    if not 1 <= strategy.signal_threshold <= 6:
        raise ValueError("signal_threshold 必須介於 1 到 6")
    if not strategy.signal_threshold < strategy.strong_signal_threshold <= 6:
        raise ValueError("strong_signal_threshold 必須大於 signal_threshold 且不超過 6")
    if strategy.pivot_left_bars < 1 or strategy.pivot_right_bars < 1:
        raise ValueError("pivot_left_bars 與 pivot_right_bars 必須大於 0")
    if not 1 <= strategy.divergence_min_separation_bars < strategy.divergence_max_separation_bars:
        raise ValueError("MACD 背離樞紐間隔設定無效")
    if strategy.divergence_expiry_bars < 0:
        raise ValueError("divergence_expiry_bars 不得小於 0")
    if strategy.risk_reward_ratio <= 0:
        raise ValueError("risk_reward_ratio 必須大於 0")
    confirmation_scans = int(raw.get("confirmation_scans", 2))
    if not 1 <= confirmation_scans <= 10:
        raise ValueError("confirmation_scans 必須介於 1 到 10")
    if not 0 < risk.risk_per_trade_pct <= 5:
        raise ValueError("risk_per_trade_pct 必須大於 0 且不超過 5")
    if min(risk.fee_rate_pct, risk.slippage_pct) < 0:
        raise ValueError("手續費與滑價假設不得小於 0")
    if risk.minimum_cost_adjusted_rr < 0 or risk.max_stop_distance_pct <= 0:
        raise ValueError("成本後盈虧比與最大停損距離設定無效")
    return AppConfig(
        symbols=symbols,
        timeframe=str(raw.get("timeframe", "15m")),
        scan_interval_seconds=int(raw.get("scan_interval_seconds", 60)),
        cvd_window_minutes=int(raw.get("cvd_window_minutes", 15)),
        cvd_stale_after_seconds=int(raw.get("cvd_stale_after_seconds", 30)),
        alert_cooldown_minutes=int(raw.get("alert_cooldown_minutes", 60)),
        confirmation_scans=confirmation_scans,
        signal_log_path=str(raw.get("signal_log_path", "data/signal_history.csv")),
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        strategy=strategy,
        risk=risk,
    )
