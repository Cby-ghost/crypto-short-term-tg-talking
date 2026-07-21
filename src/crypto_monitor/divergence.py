from __future__ import annotations

from collections.abc import Sequence

from .config import StrategyConfig
from .models import Candle, DivergenceKind, MacdDivergence


def _pivot_highs(candles: Sequence[Candle], left: int, right: int) -> list[int]:
    pivots: list[int] = []
    for index in range(left, len(candles) - right):
        value = candles[index].high
        neighbors = candles[index - left : index] + candles[index + 1 : index + right + 1]
        if all(value > candle.high for candle in neighbors):
            pivots.append(index)
    return pivots


def _pivot_lows(candles: Sequence[Candle], left: int, right: int) -> list[int]:
    pivots: list[int] = []
    for index in range(left, len(candles) - right):
        value = candles[index].low
        neighbors = candles[index - left : index] + candles[index + 1 : index + right + 1]
        if all(value < candle.low for candle in neighbors):
            pivots.append(index)
    return pivots


def detect_regular_macd_divergence(
    candles: Sequence[Candle],
    macd_line: Sequence[float],
    histogram: Sequence[float],
    atr_values: Sequence[float],
    config: StrategyConfig,
) -> MacdDivergence | None:
    if not (len(candles) == len(macd_line) == len(histogram) == len(atr_values)):
        raise ValueError("背離輸入序列長度必須一致")
    if len(candles) <= config.pivot_left_bars + config.pivot_right_bars:
        return None

    candidates: list[MacdDivergence] = []
    pivot_sets = (
        (DivergenceKind.BULLISH, _pivot_lows(candles, config.pivot_left_bars, config.pivot_right_bars)),
        (DivergenceKind.BEARISH, _pivot_highs(candles, config.pivot_left_bars, config.pivot_right_bars)),
    )
    current_index = len(candles) - 1
    for kind, pivots in pivot_sets:
        for first_position in range(len(pivots) - 1):
            for second_position in range(first_position + 1, len(pivots)):
                first = pivots[first_position]
                second = pivots[second_position]
                separation = second - first
                if not (
                    config.divergence_min_separation_bars
                    <= separation
                    <= config.divergence_max_separation_bars
                ):
                    continue
                confirmed_at = second + config.pivot_right_bars
                expires_at = confirmed_at + config.divergence_expiry_bars
                if current_index < confirmed_at or current_index > expires_at:
                    continue
                price_gap = atr_values[second] * config.divergence_min_price_atr
                macd_gap = config.divergence_min_macd_difference
                if kind == DivergenceKind.BULLISH:
                    valid = (
                        candles[second].low <= candles[first].low - price_gap
                        and macd_line[second] > macd_line[first] + macd_gap
                        and histogram[second] > histogram[first]
                    )
                    first_price, second_price, score = candles[first].low, candles[second].low, 1
                else:
                    valid = (
                        candles[second].high >= candles[first].high + price_gap
                        and macd_line[second] < macd_line[first] - macd_gap
                        and histogram[second] < histogram[first]
                    )
                    first_price, second_price, score = candles[first].high, candles[second].high, -1
                if not valid:
                    continue
                candidates.append(
                    MacdDivergence(
                        kind=kind,
                        score=score,
                        first_pivot_index=first,
                        second_pivot_index=second,
                        first_pivot_time_ms=candles[first].timestamp_ms,
                        second_pivot_time_ms=candles[second].timestamp_ms,
                        first_price=first_price,
                        second_price=second_price,
                        first_macd=macd_line[first],
                        second_macd=macd_line[second],
                        first_histogram=histogram[first],
                        second_histogram=histogram[second],
                        confirmed_at_index=confirmed_at,
                        confirmed_at_time_ms=candles[confirmed_at].timestamp_ms,
                        expires_at_index=expires_at,
                        expires_at_time_ms=(
                            candles[confirmed_at].timestamp_ms
                            + config.divergence_expiry_bars
                            * (candles[1].timestamp_ms - candles[0].timestamp_ms)
                        ),
                        bars_remaining=expires_at - current_index,
                    )
                )

    if not candidates:
        return None
    latest_confirmation = max(item.confirmed_at_index for item in candidates)
    latest = [item for item in candidates if item.confirmed_at_index == latest_confirmation]
    kinds = {item.kind for item in latest}
    if len(kinds) > 1:
        return None
    return max(latest, key=lambda item: item.second_pivot_index)
