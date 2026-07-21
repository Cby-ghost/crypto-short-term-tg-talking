from crypto_monitor.config import AppConfig, RiskConfig, StrategyConfig
from crypto_monitor.report import format_four_hour_report


def config() -> AppConfig:
    return AppConfig(
        symbols=("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"),
        timeframe="15m",
        scan_interval_seconds=60,
        cvd_window_minutes=15,
        cvd_stale_after_seconds=30,
        alert_cooldown_minutes=60,
        confirmation_scans=2,
        signal_log_path="data/signal_history.sqlite3",
        telegram_bot_token="",
        telegram_chat_id="",
        strategy=StrategyConfig(),
        risk=RiskConfig(),
    )


def test_four_hour_report_includes_latest_market_fields_and_missing_symbols() -> None:
    report = format_four_hour_report(
        config(),
        [
            {
                "symbol": "BTC-USDT-SWAP",
                "price": 100_000.0,
                "score": 5,
                "direction": "LONG",
                "spot_cvd_ratio": 0.031,
                "swap_cvd_ratio": -0.01,
                "oi_change_pct": 0.15,
                "funding_rate": 0.0001,
                "volume_ratio": 1.3,
                "macd": 123.0,
                "macd_histogram": 10.0,
                "data_gate": 1,
                "telegram_sent": 1,
                "not_sent_reason": "已發送",
            }
        ],
    )

    assert "BTC／ETH／SOL 四小時盤面報告" in report
    assert "<b>BTC-USDT-SWAP</b>｜強多單｜分數 +5" in report
    assert "CVD（現貨／合約）：+3.10%／-1.00%" in report
    assert "已發送交易通報" in report
    assert "ETH-USDT-SWAP" in report
    assert "尚無完整監控資料" in report
