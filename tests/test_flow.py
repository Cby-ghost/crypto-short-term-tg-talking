from crypto_monitor.flow import RollingCVD
from crypto_monitor.models import MarketTrade


def test_cvd_deduplicates_and_calculates_aligned_window() -> None:
    cvd = RollingCVD(window_seconds=60)
    cvd.mark_connected(now_ms=1_000)
    buy = MarketTrade("1", 10_000, 100.0, 2.0, "buy")
    sell = MarketTrade("2", 20_000, 100.0, 1.0, "sell")
    latest = MarketTrade("3", 59_000, 100.0, 1.0, "buy")
    cvd.add([buy, sell, buy, latest])

    window = cvd.window(5_000, 60_000, stale_after_seconds=2)

    assert window.ready
    assert window.quote_volume == 400.0
    assert window.ratio == 0.5


def test_cvd_is_not_ready_after_disconnect_or_incomplete_warmup() -> None:
    cvd = RollingCVD(window_seconds=60)
    cvd.mark_connected(now_ms=20_000)
    cvd.add([MarketTrade("1", 59_000, 100.0, 1.0, "buy")])
    assert not cvd.window(0, 60_000, stale_after_seconds=2).ready

    cvd.mark_disconnected()
    assert not cvd.window(0, 60_000, stale_after_seconds=2).ready
