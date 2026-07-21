import asyncio

from crypto_monitor.config import RiskConfig, StrategyConfig
from crypto_monitor.models import (
    DataQuality,
    DivergenceKind,
    FlowSnapshot,
    MacdDivergence,
    MarketSnapshot,
)
from crypto_monitor.strategy import evaluate_signal
from crypto_monitor.telegram import ConsoleClient, format_signal


def test_console_client_outputs_plain_text(capsys) -> None:
    asyncio.run(ConsoleClient().send("🟢 <b>BTC-USDT-SWAP 多單</b>"))
    assert capsys.readouterr().out.strip() == "🟢 BTC-USDT-SWAP 多單"


def test_telegram_uses_exact_order_title_and_real_divergence_values() -> None:
    divergence = MacdDivergence(
        DivergenceKind.BULLISH,
        1,
        10,
        20,
        10,
        20,
        99_200.0,
        99_000.0,
        -180.0,
        -120.0,
        -80.0,
        -40.0,
        22,
        22,
        25,
        25,
        2,
    )
    snapshot = MarketSnapshot(
        symbol="BTC-USDT-SWAP",
        timeframe="15m",
        candle_time_ms=1,
        price=100_000.0,
        ema_fast=100_100.0,
        ema_slow=99_900.0,
        macd=-100.0,
        macd_signal=-120.0,
        macd_histogram=20.0,
        previous_macd_histogram=10.0,
        atr=300.0,
        oi_change_pct=0.8,
        funding_rate=0.0,
        flow=FlowSnapshot(0.062, -0.035, 1_000.0, 1_000.0, True),
        previous_close=99_900.0,
        volume_ratio=1.45,
        divergence=divergence,
        data_quality=DataQuality(True, True, True, True),
    )
    risk = RiskConfig()
    signal = evaluate_signal(snapshot, StrategyConfig(), risk)

    message = format_signal(signal, snapshot, risk)

    assert "BTC-USDT-SWAP 強多單" in message
    assert "可考慮做多" not in message
    assert "可考慮做空" not in message
    assert "止盈：" in message
    assert "止盈一" not in message and "止盈二" not in message
    assert "99,200.00→99,000.00" in message
    assert "-180→-120" in message
    assert "【風險與反對理由】" in message
    assert "【訊號失效】" in message
