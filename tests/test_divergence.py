from crypto_monitor.config import StrategyConfig
from crypto_monitor.divergence import detect_regular_macd_divergence
from crypto_monitor.models import Candle, DivergenceKind


def series(length: int = 15) -> tuple[list[Candle], list[float], list[float], list[float]]:
    candles = [Candle(i, 10.0, 11.0, 9.0, 10.0, 100.0) for i in range(length)]
    macd = [0.0] * length
    histogram = [0.0] * length
    atr = [1.0] * length
    return candles, macd, histogram, atr


def test_regular_bullish_macd_divergence() -> None:
    candles, macd, histogram, atr = series()
    candles[4] = Candle(4, 10.0, 11.0, 7.0, 10.0, 100.0)
    candles[10] = Candle(10, 10.0, 11.0, 6.0, 10.0, 100.0)
    macd[4], macd[10] = -2.0, -1.0
    histogram[4], histogram[10] = -0.8, -0.4

    result = detect_regular_macd_divergence(
        candles, macd, histogram, atr, StrategyConfig()
    )

    assert result is not None
    assert result.kind == DivergenceKind.BULLISH
    assert result.first_price == 7.0
    assert result.second_price == 6.0
    assert result.bars_remaining == 1


def test_regular_bearish_macd_divergence() -> None:
    candles, macd, histogram, atr = series()
    candles[4] = Candle(4, 10.0, 13.0, 9.0, 10.0, 100.0)
    candles[10] = Candle(10, 10.0, 14.0, 9.0, 10.0, 100.0)
    macd[4], macd[10] = 2.0, 1.0
    histogram[4], histogram[10] = 0.8, 0.4

    result = detect_regular_macd_divergence(
        candles, macd, histogram, atr, StrategyConfig()
    )

    assert result is not None
    assert result.kind == DivergenceKind.BEARISH
    assert result.first_price == 13.0
    assert result.second_price == 14.0


def test_no_divergence_when_macd_does_not_confirm() -> None:
    candles, macd, histogram, atr = series()
    candles[4] = Candle(4, 10.0, 11.0, 7.0, 10.0, 100.0)
    candles[10] = Candle(10, 10.0, 11.0, 6.0, 10.0, 100.0)
    macd[4], macd[10] = -1.0, -2.0
    histogram[4], histogram[10] = -0.4, -0.8

    assert detect_regular_macd_divergence(
        candles, macd, histogram, atr, StrategyConfig()
    ) is None


def test_unconfirmed_right_bars_do_not_create_lookahead_signal() -> None:
    candles, macd, histogram, atr = series(length=12)
    candles[4] = Candle(4, 10.0, 11.0, 7.0, 10.0, 100.0)
    candles[10] = Candle(10, 10.0, 11.0, 6.0, 10.0, 100.0)
    macd[4], macd[10] = -2.0, -1.0
    histogram[4], histogram[10] = -0.8, -0.4

    assert detect_regular_macd_divergence(
        candles, macd, histogram, atr, StrategyConfig()
    ) is None


def test_expired_divergence_is_not_returned() -> None:
    candles, macd, histogram, atr = series(length=17)
    candles[4] = Candle(4, 10.0, 11.0, 7.0, 10.0, 100.0)
    candles[10] = Candle(10, 10.0, 11.0, 6.0, 10.0, 100.0)
    macd[4], macd[10] = -2.0, -1.0
    histogram[4], histogram[10] = -0.8, -0.4

    assert detect_regular_macd_divergence(
        candles, macd, histogram, atr, StrategyConfig()
    ) is None


def test_same_pivot_pair_has_a_stable_deduplication_key() -> None:
    candles, macd, histogram, atr = series()
    candles[4] = Candle(4, 10.0, 11.0, 7.0, 10.0, 100.0)
    candles[10] = Candle(10, 10.0, 11.0, 6.0, 10.0, 100.0)
    macd[4], macd[10] = -2.0, -1.0
    histogram[4], histogram[10] = -0.8, -0.4

    first = detect_regular_macd_divergence(
        candles, macd, histogram, atr, StrategyConfig()
    )
    second = detect_regular_macd_divergence(
        candles, macd, histogram, atr, StrategyConfig()
    )

    assert first is not None and second is not None
    assert first.key == second.key
