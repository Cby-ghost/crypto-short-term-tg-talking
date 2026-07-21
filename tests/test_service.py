from datetime import datetime, timezone

from crypto_monitor.config import AppConfig, RiskConfig, StrategyConfig
from crypto_monitor.models import Candle, Direction, OpenInterestSnapshot
from crypto_monitor.service import MonitorService


class FakeOKX:
    def __init__(self) -> None:
        self.requested_bars: list[str] = []
        self._candles = [
            Candle(
                timestamp_ms=index * 900_000,
                open=99.5 + index,
                high=100.5 + index,
                low=99.0 + index,
                close=100.0 + index,
                volume=100.0,
            )
            for index in range(200)
        ]

    async def candles(self, symbol: str, bar: str, limit: int = 200) -> list[Candle]:
        self.requested_bars.append(bar)
        return self._candles

    async def open_interest(self, symbol: str) -> OpenInterestSnapshot:
        return OpenInterestSnapshot(
            1_000.0, self._candles[-1].timestamp_ms + 900_000
        )

    async def funding_rate(self, symbol: str) -> float:
        return 0.0


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)


def config(tmp_path, confirmation_scans: int = 2) -> AppConfig:
    return AppConfig(
        symbols=("BTC-USDT-SWAP",),
        timeframe="15m",
        scan_interval_seconds=60,
        cvd_window_minutes=15,
        cvd_stale_after_seconds=30,
        alert_cooldown_minutes=60,
        confirmation_scans=confirmation_scans,
        signal_log_path=str(tmp_path / "signals.sqlite3"),
        telegram_bot_token="test-token",
        telegram_chat_id="test-chat",
        strategy=StrategyConfig(),
        risk=RiskConfig(),
    )


def test_scan_uses_only_confirmed_15_minute_candles(tmp_path) -> None:
    okx = FakeOKX()
    telegram = FakeTelegram()
    service = MonitorService(config(tmp_path), okx, telegram)  # type: ignore[arg-type]

    import asyncio

    asyncio.run(service._scan_symbol("BTC-USDT-SWAP"))

    assert okx.requested_bars == ["15m"]
    assert (tmp_path / "signals.sqlite3").exists()
    assert telegram.messages == []


def test_same_candle_does_not_count_as_two_confirmations(tmp_path) -> None:
    service = MonitorService(
        config(tmp_path), FakeOKX(), FakeTelegram()  # type: ignore[arg-type]
    )
    first = 1_000_000

    assert not service._confirmed("BTC-USDT-SWAP", Direction.LONG, first)
    assert not service._confirmed("BTC-USDT-SWAP", Direction.LONG, first)
    assert service._confirmed("BTC-USDT-SWAP", Direction.LONG, first + 900_000)


def test_nonconsecutive_candle_resets_confirmation(tmp_path) -> None:
    service = MonitorService(
        config(tmp_path), FakeOKX(), FakeTelegram()  # type: ignore[arg-type]
    )
    first = 1_000_000
    assert not service._confirmed("BTC-USDT-SWAP", Direction.SHORT, first)
    assert not service._confirmed("BTC-USDT-SWAP", Direction.SHORT, first + 1_800_000)


def test_strong_upgrade_can_bypass_cooldown(tmp_path) -> None:
    service = MonitorService(
        config(tmp_path), FakeOKX(), FakeTelegram()  # type: ignore[arg-type]
    )

    class StrongSignal:
        direction = Direction.LONG
        score = 5
        is_strong = True

    service.episode_alert["BTC-USDT-SWAP"] = (Direction.LONG, 4, False)
    service.last_alert[("BTC-USDT-SWAP", Direction.LONG)] = datetime.now(timezone.utc)

    assert service._should_send_update("BTC-USDT-SWAP", StrongSignal())[0]  # type: ignore[arg-type]
