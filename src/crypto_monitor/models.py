from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


@dataclass(frozen=True)
class Candle:
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class MarketTrade:
    trade_id: str
    timestamp_ms: int
    price: float
    size: float
    side: str

    @property
    def quote_value(self) -> float:
        return self.price * self.size


@dataclass(frozen=True)
class OpenInterestSnapshot:
    value: float
    timestamp_ms: int


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class DivergenceKind(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


@dataclass(frozen=True)
class MacdDivergence:
    kind: DivergenceKind
    score: int
    first_pivot_index: int
    second_pivot_index: int
    first_pivot_time_ms: int
    second_pivot_time_ms: int
    first_price: float
    second_price: float
    first_macd: float
    second_macd: float
    first_histogram: float
    second_histogram: float
    confirmed_at_index: int
    confirmed_at_time_ms: int
    expires_at_index: int
    expires_at_time_ms: int
    bars_remaining: int

    @property
    def key(self) -> str:
        return f"{self.kind.value}:{self.first_pivot_time_ms}:{self.second_pivot_time_ms}"


@dataclass(frozen=True)
class FlowSnapshot:
    spot_cvd_ratio: float
    swap_cvd_ratio: float
    spot_quote_volume: float
    swap_quote_volume: float
    ready: bool = True


@dataclass(frozen=True)
class DataQuality:
    candles_confirmed: bool
    cvd_complete: bool
    oi_aligned: bool
    api_fresh: bool
    issues: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return (
            self.candles_confirmed
            and self.cvd_complete
            and self.oi_aligned
            and self.api_fresh
            and not self.issues
        )


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    timeframe: str
    candle_time_ms: int
    price: float
    ema_fast: float
    ema_slow: float
    macd: float
    macd_signal: float
    macd_histogram: float
    previous_macd_histogram: float
    atr: float
    oi_change_pct: float
    funding_rate: float
    flow: FlowSnapshot
    previous_close: float
    volume_ratio: float
    divergence: MacdDivergence | None
    data_quality: DataQuality


@dataclass(frozen=True)
class IndicatorVote:
    name: str
    score: int
    reason: str
    group: str


@dataclass(frozen=True)
class GateStatus:
    direction_confirmed: bool
    funds_confirmed: bool
    independent_groups_confirmed: bool
    data_quality_confirmed: bool
    supporting_groups: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return (
            self.direction_confirmed
            and self.funds_confirmed
            and self.independent_groups_confirmed
            and self.data_quality_confirmed
        )


@dataclass(frozen=True)
class Signal:
    symbol: str
    direction: Direction
    score: int
    base_score: int
    funding_adjustment: int
    threshold: int
    strong_threshold: int
    entry: float
    stop_loss: float
    take_profit: float
    price_rr: float
    cost_adjusted_rr: float
    reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    votes: tuple[IndicatorVote, ...] = field(default_factory=tuple)
    group_scores: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    gates: GateStatus | None = None
    invalidation: str = ""
    blocked_reasons: tuple[str, ...] = field(default_factory=tuple)
    position_size_base: float | None = None
    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def is_strong(self) -> bool:
        return abs(self.score) >= self.strong_threshold

    @property
    def notification_title(self) -> str:
        if self.direction == Direction.LONG:
            return "強多單" if self.is_strong else "多單"
        if self.direction == Direction.SHORT:
            return "強空單" if self.is_strong else "空單"
        return "中性"

    @property
    def eligible(self) -> bool:
        return (
            self.direction != Direction.NEUTRAL
            and self.gates is not None
            and self.gates.passed
            and not self.blocked_reasons
        )
