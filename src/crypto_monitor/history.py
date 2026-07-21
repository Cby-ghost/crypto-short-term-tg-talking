from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import RiskConfig
from .models import Candle, Direction, MarketSnapshot, Signal


class SignalHistory:
    def __init__(self, path: str, risk: RiskConfig) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.risk = risk
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS signal_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at_utc TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    candle_time_ms INTEGER NOT NULL,
                    price REAL NOT NULL,
                    score INTEGER NOT NULL,
                    base_score INTEGER NOT NULL,
                    funding_adjustment INTEGER NOT NULL,
                    direction TEXT NOT NULL,
                    spot_cvd_ratio REAL NOT NULL DEFAULT 0,
                    swap_cvd_ratio REAL NOT NULL DEFAULT 0,
                    oi_change_pct REAL NOT NULL DEFAULT 0,
                    funding_rate REAL NOT NULL DEFAULT 0,
                    volume_ratio REAL NOT NULL DEFAULT 0,
                    macd REAL NOT NULL DEFAULT 0,
                    macd_histogram REAL NOT NULL DEFAULT 0,
                    votes_json TEXT NOT NULL,
                    group_scores_json TEXT NOT NULL,
                    divergence_type TEXT,
                    first_pivot_price REAL,
                    second_pivot_price REAL,
                    first_pivot_macd REAL,
                    second_pivot_macd REAL,
                    divergence_confirmed_at_ms INTEGER,
                    divergence_expires_at_ms INTEGER,
                    direction_gate INTEGER NOT NULL,
                    funds_gate INTEGER NOT NULL,
                    groups_gate INTEGER NOT NULL,
                    data_gate INTEGER NOT NULL,
                    telegram_sent INTEGER NOT NULL,
                    not_sent_reason TEXT NOT NULL,
                    entry REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    fee_rate_pct REAL NOT NULL,
                    slippage_pct REAL NOT NULL,
                    return_1 REAL,
                    return_4 REAL,
                    return_8 REAL,
                    return_16 REAL,
                    mfe REAL,
                    mae REAL,
                    UNIQUE(symbol, candle_time_ms)
                )
                """
            )
            existing_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(signal_history)")
            }
            for name, definition in {
                "spot_cvd_ratio": "REAL NOT NULL DEFAULT 0",
                "swap_cvd_ratio": "REAL NOT NULL DEFAULT 0",
                "oi_change_pct": "REAL NOT NULL DEFAULT 0",
                "funding_rate": "REAL NOT NULL DEFAULT 0",
                "volume_ratio": "REAL NOT NULL DEFAULT 0",
                "macd": "REAL NOT NULL DEFAULT 0",
                "macd_histogram": "REAL NOT NULL DEFAULT 0",
            }.items():
                if name not in existing_columns:
                    connection.execute(f"ALTER TABLE signal_history ADD COLUMN {name} {definition}")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def record(
        self,
        snapshot: MarketSnapshot,
        signal: Signal,
        telegram_sent: bool,
        not_sent_reason: str,
    ) -> None:
        divergence = snapshot.divergence
        gates = signal.gates
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO signal_history (
                    recorded_at_utc, symbol, timeframe, candle_time_ms, price,
                    score, base_score, funding_adjustment, direction,
                    spot_cvd_ratio, swap_cvd_ratio, oi_change_pct, funding_rate,
                    volume_ratio, macd, macd_histogram, votes_json,
                    group_scores_json, divergence_type, first_pivot_price,
                    second_pivot_price, first_pivot_macd, second_pivot_macd,
                    divergence_confirmed_at_ms, divergence_expires_at_ms,
                    direction_gate, funds_gate, groups_gate, data_gate,
                    telegram_sent, not_sent_reason, entry, stop_loss, take_profit,
                    fee_rate_pct, slippage_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    snapshot.symbol,
                    snapshot.timeframe,
                    snapshot.candle_time_ms,
                    snapshot.price,
                    signal.score,
                    signal.base_score,
                    signal.funding_adjustment,
                    signal.direction.value,
                    snapshot.flow.spot_cvd_ratio,
                    snapshot.flow.swap_cvd_ratio,
                    snapshot.oi_change_pct,
                    snapshot.funding_rate,
                    snapshot.volume_ratio,
                    snapshot.macd,
                    snapshot.macd_histogram,
                    json.dumps(
                        [
                            {"name": vote.name, "score": vote.score, "reason": vote.reason}
                            for vote in signal.votes
                        ],
                        ensure_ascii=False,
                    ),
                    json.dumps(dict(signal.group_scores), ensure_ascii=False),
                    divergence.kind.value if divergence else None,
                    divergence.first_price if divergence else None,
                    divergence.second_price if divergence else None,
                    divergence.first_macd if divergence else None,
                    divergence.second_macd if divergence else None,
                    divergence.confirmed_at_time_ms if divergence else None,
                    divergence.expires_at_time_ms if divergence else None,
                    int(bool(gates and gates.direction_confirmed)),
                    int(bool(gates and gates.funds_confirmed)),
                    int(bool(gates and gates.independent_groups_confirmed)),
                    int(bool(gates and gates.data_quality_confirmed)),
                    int(telegram_sent),
                    not_sent_reason,
                    signal.entry,
                    signal.stop_loss,
                    signal.take_profit,
                    self.risk.fee_rate_pct,
                    self.risk.slippage_pct,
                ),
            )

    def latest_market_rows(self, symbols: tuple[str, ...]) -> list[dict[str, object]]:
        columns = (
            "symbol, timeframe, candle_time_ms, recorded_at_utc, price, score, direction, "
            "spot_cvd_ratio, swap_cvd_ratio, oi_change_pct, funding_rate, volume_ratio, "
            "macd, macd_histogram, data_gate, telegram_sent, not_sent_reason"
        )
        rows: list[dict[str, object]] = []
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            for symbol in symbols:
                row = connection.execute(
                    f"SELECT {columns} FROM signal_history WHERE symbol = ? "
                    "ORDER BY candle_time_ms DESC LIMIT 1",
                    (symbol,),
                ).fetchone()
                if row is not None:
                    rows.append(dict(row))
        return rows

    def update_outcomes(self, symbol: str, candles: list[Candle]) -> None:
        index_by_time = {candle.timestamp_ms: index for index, candle in enumerate(candles)}
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, candle_time_ms, entry, direction,
                       return_1, return_4, return_8, return_16, mfe, mae
                FROM signal_history WHERE symbol = ?
                """,
                (symbol,),
            ).fetchall()
            for row in rows:
                record_id, candle_time, entry, direction, *existing = row
                start = index_by_time.get(candle_time)
                if start is None:
                    continue
                values = list(existing)
                changed = False
                for position, horizon in enumerate((1, 4, 8, 16)):
                    if values[position] is None and start + horizon < len(candles):
                        values[position] = (candles[start + horizon].close / entry - 1) * 100
                        changed = True
                if start + 16 < len(candles) and (values[4] is None or values[5] is None):
                    future = candles[start + 1 : start + 17]
                    if direction == Direction.SHORT.value:
                        values[4] = (entry - min(candle.low for candle in future)) / entry * 100
                        values[5] = (entry - max(candle.high for candle in future)) / entry * 100
                    else:
                        values[4] = (max(candle.high for candle in future) / entry - 1) * 100
                        values[5] = (min(candle.low for candle in future) / entry - 1) * 100
                    changed = True
                if changed:
                    connection.execute(
                        """
                        UPDATE signal_history
                        SET return_1 = ?, return_4 = ?, return_8 = ?, return_16 = ?, mfe = ?, mae = ?
                        WHERE id = ?
                        """,
                        (*values, record_id),
                    )
