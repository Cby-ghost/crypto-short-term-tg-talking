from __future__ import annotations

from collections.abc import Sequence

from .models import Candle


def ema(values: Sequence[float], period: int) -> list[float]:
    if period <= 0 or len(values) < period:
        raise ValueError("EMA 資料筆數不足或週期無效")
    seed = sum(values[:period]) / period
    result = [seed] * period
    multiplier = 2 / (period + 1)
    for value in values[period:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def macd(
    values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float], list[float], list[float]]:
    if len(values) < slow + signal:
        raise ValueError("MACD 資料筆數不足")
    fast_line = ema(values, fast)
    slow_line = ema(values, slow)
    macd_line = [fast_line[i] - slow_line[i] for i in range(len(values))]
    signal_line = ema(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, histogram


def atr(candles: Sequence[Candle], period: int = 14) -> list[float]:
    if len(candles) <= period:
        raise ValueError("ATR 資料筆數不足")
    true_ranges = [candles[0].high - candles[0].low]
    for previous, current in zip(candles, candles[1:]):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    initial = sum(true_ranges[:period]) / period
    output = [initial] * period
    for value in true_ranges[period:]:
        output.append((output[-1] * (period - 1) + value) / period)
    return output
