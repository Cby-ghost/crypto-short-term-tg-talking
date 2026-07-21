import sqlite3

import pytest

from crypto_monitor.config import RiskConfig, StrategyConfig
from crypto_monitor.history import SignalHistory
from crypto_monitor.models import (
    DataQuality,
    Direction,
    DivergenceKind,
    FlowSnapshot,
    Candle,
    MacdDivergence,
    MarketSnapshot,
)
from crypto_monitor.strategy import build_votes, evaluate_signal, score_groups


def divergence(kind: DivergenceKind = DivergenceKind.BULLISH) -> MacdDivergence:
    bullish = kind == DivergenceKind.BULLISH
    return MacdDivergence(
        kind=kind,
        score=1 if bullish else -1,
        first_pivot_index=10,
        second_pivot_index=20,
        first_pivot_time_ms=10,
        second_pivot_time_ms=20,
        first_price=104.0 if bullish else 96.0,
        second_price=103.0 if bullish else 97.0,
        first_macd=-2.0 if bullish else 2.0,
        second_macd=-1.0 if bullish else 1.0,
        first_histogram=-0.8 if bullish else 0.8,
        second_histogram=-0.4 if bullish else 0.4,
        confirmed_at_index=22,
        confirmed_at_time_ms=22,
        expires_at_index=25,
        expires_at_time_ms=25,
        bars_remaining=2,
    )


def snapshot(**changes: object) -> MarketSnapshot:
    values: dict[str, object] = {
        "symbol": "BTC-USDT-SWAP",
        "timeframe": "15m",
        "candle_time_ms": 1,
        "price": 105.0,
        "ema_fast": 103.0,
        "ema_slow": 100.0,
        "macd": 2.0,
        "macd_signal": 1.0,
        "macd_histogram": 1.0,
        "previous_macd_histogram": 0.5,
        "atr": 2.0,
        "oi_change_pct": 0.5,
        "funding_rate": 0.0,
        "flow": FlowSnapshot(0.1, -0.1, 1_000.0, 1_000.0, True),
        "previous_close": 100.0,
        "volume_ratio": 1.5,
        "divergence": divergence(),
        "data_quality": DataQuality(True, True, True, True),
    }
    values.update(changes)
    return MarketSnapshot(**values)  # type: ignore[arg-type]


def bearish_snapshot(**changes: object) -> MarketSnapshot:
    values: dict[str, object] = {
        "price": 95.0,
        "ema_fast": 97.0,
        "ema_slow": 100.0,
        "macd": -2.0,
        "macd_signal": -1.0,
        "macd_histogram": -1.0,
        "previous_macd_histogram": -0.5,
        "oi_change_pct": 0.5,
        "flow": FlowSnapshot(-0.1, 0.1, 1_000.0, 1_000.0, True),
        "previous_close": 100.0,
        "volume_ratio": 1.5,
        "divergence": divergence(DivergenceKind.BEARISH),
    }
    values.update(changes)
    return snapshot(**values)


def test_regular_votes_are_only_minus_one_zero_or_plus_one() -> None:
    votes = build_votes(snapshot(), StrategyConfig())
    assert len(votes) == 8
    assert all(vote.score in (-1, 0, 1) for vote in votes)


def test_macd_and_flow_group_caps() -> None:
    votes = build_votes(snapshot(), StrategyConfig())
    groups = score_groups(votes)
    assert groups["momentum"] == 1
    assert abs(groups["flow"]) <= 2

    all_bullish_flow = build_votes(
        snapshot(flow=FlowSnapshot(0.1, 0.1, 1_000.0, 1_000.0, True)),
        StrategyConfig(),
    )
    assert score_groups(all_bullish_flow)["flow"] == 2


def test_bullish_bearish_and_neutral_signals() -> None:
    long_signal = evaluate_signal(snapshot(), StrategyConfig(), RiskConfig())
    short_signal = evaluate_signal(bearish_snapshot(), StrategyConfig(), RiskConfig())
    neutral_signal = evaluate_signal(
        snapshot(
            price=100.0,
            previous_close=100.0,
            ema_fast=100.0,
            ema_slow=100.0,
            macd_histogram=0.0,
            previous_macd_histogram=0.0,
            oi_change_pct=0.0,
            flow=FlowSnapshot(0.0, 0.0, 1_000.0, 1_000.0, True),
            volume_ratio=1.0,
            divergence=None,
        ),
        StrategyConfig(),
        RiskConfig(),
    )

    assert long_signal.direction == Direction.LONG
    assert long_signal.eligible
    assert short_signal.direction == Direction.SHORT
    assert short_signal.eligible
    assert neutral_signal.direction == Direction.NEUTRAL


def test_funding_only_reduces_the_crowded_direction() -> None:
    config = StrategyConfig()
    risk = RiskConfig()
    bullish = evaluate_signal(snapshot(funding_rate=0.0), config, risk)
    crowded_bullish = evaluate_signal(snapshot(funding_rate=0.001), config, risk)
    negative_funding_bullish = evaluate_signal(snapshot(funding_rate=-0.001), config, risk)
    bearish = evaluate_signal(bearish_snapshot(funding_rate=0.0), config, risk)
    crowded_bearish = evaluate_signal(bearish_snapshot(funding_rate=-0.001), config, risk)
    positive_funding_bearish = evaluate_signal(bearish_snapshot(funding_rate=0.001), config, risk)

    assert crowded_bullish.score == bullish.score - 1
    assert crowded_bullish.notification_title == "多單"
    assert negative_funding_bullish.score == bullish.score
    assert crowded_bearish.score == bearish.score + 1
    assert crowded_bearish.notification_title == "空單"
    assert positive_funding_bearish.score == bearish.score


def test_data_failure_and_direction_gate_block_notification() -> None:
    data_failure = evaluate_signal(
        snapshot(data_quality=DataQuality(True, False, True, True, ("CVD 未就緒",))),
        StrategyConfig(),
        RiskConfig(),
    )
    no_direction = evaluate_signal(
        snapshot(ema_fast=100.0, ema_slow=100.0, divergence=None),
        StrategyConfig(),
        RiskConfig(),
    )

    assert data_failure.direction == Direction.LONG
    assert not data_failure.eligible
    assert "CVD 未就緒" in data_failure.blocked_reasons
    assert no_direction.direction == Direction.LONG
    assert no_direction.gates is not None
    assert not no_direction.gates.direction_confirmed


def test_single_take_profit_is_one_to_one_and_stops_are_valid() -> None:
    long_signal = evaluate_signal(snapshot(divergence=None), StrategyConfig(), RiskConfig())
    short_signal = evaluate_signal(
        bearish_snapshot(divergence=None), StrategyConfig(), RiskConfig()
    )

    assert long_signal.stop_loss < long_signal.entry < long_signal.take_profit
    assert long_signal.take_profit - long_signal.entry == pytest.approx(
        long_signal.entry - long_signal.stop_loss
    )
    assert short_signal.take_profit < short_signal.entry < short_signal.stop_loss
    assert short_signal.entry - short_signal.take_profit == pytest.approx(
        short_signal.stop_loss - short_signal.entry
    )


def test_position_size_uses_fixed_account_risk() -> None:
    signal = evaluate_signal(
        snapshot(divergence=None),
        StrategyConfig(),
        RiskConfig(account_equity_usdt=10_000, risk_per_trade_pct=1),
    )
    assert signal.position_size_base == pytest.approx(
        100 / (signal.entry - signal.stop_loss)
    )


def test_sqlite_history_updates_forward_returns_and_mfe_mae(tmp_path) -> None:
    risk = RiskConfig()
    current = snapshot(divergence=None, candle_time_ms=1, price=100.0)
    signal = evaluate_signal(current, StrategyConfig(), risk)
    path = tmp_path / "history.sqlite3"
    history = SignalHistory(str(path), risk)
    history.record(current, signal, False, "測試")
    candles = [
        Candle(1 + index, 100.0 + index, 101.0 + index, 99.0 + index, 100.0 + index, 1.0)
        for index in range(17)
    ]

    history.update_outcomes(current.symbol, candles)

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT return_1, return_4, return_8, return_16, mfe, mae FROM signal_history"
        ).fetchone()
    assert row is not None
    assert all(value is not None for value in row)


def test_sqlite_history_returns_the_latest_row_for_each_requested_symbol(tmp_path) -> None:
    risk = RiskConfig()
    path = tmp_path / "history.sqlite3"
    history = SignalHistory(str(path), risk)
    first = snapshot(divergence=None, candle_time_ms=1, price=100.0)
    latest = snapshot(divergence=None, candle_time_ms=2, price=110.0)

    history.record(first, evaluate_signal(first, StrategyConfig(), risk), False, "未達門檻")
    history.record(latest, evaluate_signal(latest, StrategyConfig(), risk), True, "已發送")

    rows = history.latest_market_rows(("BTC-USDT-SWAP", "ETH-USDT-SWAP"))

    assert len(rows) == 1
    assert rows[0]["candle_time_ms"] == 2
    assert rows[0]["price"] == 110.0
    assert rows[0]["spot_cvd_ratio"] == 0.1
