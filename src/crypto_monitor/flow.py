from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from .models import MarketTrade


@dataclass(frozen=True)
class CVDWindow:
    ratio: float
    quote_volume: float
    ready: bool


@dataclass
class RollingCVD:
    window_seconds: int
    _trades: deque[MarketTrade] = field(default_factory=deque)
    _seen: set[str] = field(default_factory=set)
    _connected_since_ms: int | None = None
    _last_trade_ms: int | None = None

    def mark_connected(self, now_ms: int | None = None) -> None:
        self._trades.clear()
        self._seen.clear()
        self._last_trade_ms = None
        self._connected_since_ms = now_ms if now_ms is not None else int(time.time() * 1000)

    def mark_disconnected(self) -> None:
        self._connected_since_ms = None
        self._last_trade_ms = None
        self._trades.clear()
        self._seen.clear()

    def add(self, trades: list[MarketTrade]) -> None:
        for trade in sorted(trades, key=lambda item: item.timestamp_ms):
            if trade.trade_id in self._seen:
                continue
            self._seen.add(trade.trade_id)
            self._trades.append(trade)
            self._last_trade_ms = max(self._last_trade_ms or 0, trade.timestamp_ms)
        self.prune(now_ms=self._last_trade_ms)

    def prune(self, now_ms: int | None = None) -> None:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        retention_seconds = self.window_seconds + 300
        cutoff = now - retention_seconds * 1000
        while self._trades and self._trades[0].timestamp_ms < cutoff:
            expired = self._trades.popleft()
            self._seen.discard(expired.trade_id)

    def window(self, start_ms: int, end_ms: int, stale_after_seconds: int) -> CVDWindow:
        selected = [trade for trade in self._trades if start_ms <= trade.timestamp_ms < end_ms]
        quote_volume = sum(trade.quote_value for trade in selected)
        delta = sum(
            trade.quote_value if trade.side == "buy" else -trade.quote_value
            for trade in selected
        )
        connected_for_full_window = (
            self._connected_since_ms is not None and self._connected_since_ms <= start_ms
        )
        stream_fresh = (
            self._last_trade_ms is not None
            and self._last_trade_ms >= end_ms - stale_after_seconds * 1000
        )
        return CVDWindow(
            ratio=delta / quote_volume if quote_volume else 0.0,
            quote_volume=quote_volume,
            ready=connected_for_full_window and stream_fresh and quote_volume > 0,
        )

    @property
    def quote_volume(self) -> float:
        return sum(trade.quote_value for trade in self._trades)

    @property
    def delta(self) -> float:
        return sum(
            trade.quote_value if trade.side == "buy" else -trade.quote_value
            for trade in self._trades
        )

    @property
    def ratio(self) -> float:
        total = self.quote_volume
        return self.delta / total if total else 0.0
