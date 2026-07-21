import pytest

from crypto_monitor.indicators import atr, ema, macd
from crypto_monitor.models import Candle


def test_ema_tracks_uptrend() -> None:
    values = [float(value) for value in range(1, 31)]
    result = ema(values, 5)
    assert len(result) == len(values)
    assert result[-1] > result[-2]
    assert result[-1] < values[-1]


def test_macd_output_lengths_match() -> None:
    values = [100 + value * 0.5 for value in range(80)]
    line, signal, histogram = macd(values)
    assert len(line) == len(signal) == len(histogram) == len(values)


def test_atr_constant_range() -> None:
    candles = [Candle(i, 9.0, 11.0, 9.0, 10.0, 100.0) for i in range(30)]
    assert atr(candles, 14)[-1] == pytest.approx(2.0)
