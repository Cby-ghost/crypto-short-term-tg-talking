from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import aiohttp

from .config import AppConfig
from .divergence import detect_regular_macd_divergence
from .flow import RollingCVD
from .history import SignalHistory
from .indicators import atr, ema, macd
from .models import (
    DataQuality,
    Direction,
    FlowSnapshot,
    MarketSnapshot,
    MarketTrade,
    OpenInterestSnapshot,
    Signal,
)
from .okx import OKXClient, spot_symbol
from .strategy import evaluate_signal
from .telegram import ConsoleClient, NotificationClient, TelegramClient, format_signal

LOGGER = logging.getLogger(__name__)


def timeframe_to_ms(timeframe: str) -> int:
    unit = timeframe[-1]
    value = int(timeframe[:-1])
    if unit == "m":
        return value * 60_000
    if unit in ("H", "h"):
        return value * 3_600_000
    raise ValueError(f"不支援的 K 線週期：{timeframe}")


class MonitorService:
    def __init__(
        self,
        config: AppConfig,
        okx: OKXClient,
        telegram: NotificationClient,
    ) -> None:
        self.config = config
        self.okx = okx
        self.telegram = telegram
        window = config.cvd_window_minutes * 60
        self.flows = {
            symbol: {"spot": RollingCVD(window), "swap": RollingCVD(window)}
            for symbol in config.symbols
        }
        self.flow_routes = {
            spot_symbol(symbol): (symbol, "spot") for symbol in config.symbols
        } | {symbol: (symbol, "swap") for symbol in config.symbols}
        self.oi_samples: dict[str, tuple[int, OpenInterestSnapshot]] = {}
        self.last_processed_candle: dict[str, int] = {}
        self.last_alert: dict[tuple[str, Direction], datetime] = {}
        self.pending_direction: dict[str, tuple[Direction, int, int]] = {}
        self.episode_alert: dict[str, tuple[Direction, int, bool]] = {}
        self.notified_divergences: set[str] = set()
        self.history = SignalHistory(config.signal_log_path, config.risk)

    async def run(self) -> None:
        await self.telegram.send(
            "✅ <b>虛擬貨幣監控已啟動</b>\n"
            f"標的：{', '.join(self.config.symbols)}\n"
            f"週期：{self.config.timeframe}｜訊號門檻：±{self.config.strategy.signal_threshold}\n"
            "目前只推播提醒，不會自動下單。"
        )
        await asyncio.gather(self._trade_stream_loop(), self._scan_loop())

    async def _trade_stream_loop(self) -> None:
        await self.okx.stream_all_trades(
            tuple(self.flow_routes), self._on_trade, self._on_stream_state_change
        )

    def _on_trade(self, instrument: str, trade: MarketTrade) -> None:
        route = self.flow_routes.get(instrument)
        if route:
            self.flows[route[0]][route[1]].add([trade])

    def _on_stream_state_change(self, connected: bool) -> None:
        now_ms = int(time.time() * 1000)
        for markets in self.flows.values():
            for flow in markets.values():
                if connected:
                    flow.mark_connected(now_ms)
                else:
                    flow.mark_disconnected()

    async def _scan_loop(self) -> None:
        await asyncio.sleep(min(10, self.config.scan_interval_seconds))
        while True:
            await self.scan_once()
            await asyncio.sleep(self.config.scan_interval_seconds)

    async def scan_once(self) -> None:
        results = await asyncio.gather(
            *(self._scan_symbol(symbol) for symbol in self.config.symbols),
            return_exceptions=True,
        )
        for symbol, result in zip(self.config.symbols, results):
            if isinstance(result, Exception):
                LOGGER.error("掃描 %s 失敗：%s", symbol, result)

    async def _scan_symbol(self, symbol: str) -> None:
        candles, current_oi, funding = await asyncio.gather(
            self.okx.candles(symbol, self.config.timeframe, 200),
            self.okx.open_interest(symbol),
            self.okx.funding_rate(symbol),
        )
        minimum = max(
            self.config.strategy.ema_slow + 10,
            self.config.strategy.macd_slow + self.config.strategy.macd_signal + 10,
            self.config.strategy.divergence_max_separation_bars
            + self.config.strategy.pivot_left_bars
            + self.config.strategy.pivot_right_bars
            + 10,
            60,
        )
        if len(candles) < minimum:
            raise RuntimeError(f"{symbol} 已收 K 線不足：{len(candles)} < {minimum}")
        latest = candles[-1]
        if self.last_processed_candle.get(symbol) == latest.timestamp_ms:
            return

        frame_ms = timeframe_to_ms(self.config.timeframe)
        candle_end_ms = latest.timestamp_ms + frame_ms
        self.history.update_outcomes(symbol, candles)

        previous_oi = self.oi_samples.get(symbol)
        oi_aligned = bool(
            previous_oi and previous_oi[0] == latest.timestamp_ms - frame_ms
        )
        oi_change = (
            (current_oi.value / previous_oi[1].value - 1) * 100
            if oi_aligned and previous_oi and previous_oi[1].value > 0
            else 0.0
        )
        self.oi_samples[symbol] = (latest.timestamp_ms, current_oi)
        oi_timestamp_fresh = abs(current_oi.timestamp_ms - candle_end_ms) <= (
            self.config.scan_interval_seconds + self.config.cvd_stale_after_seconds
        ) * 1000
        oi_aligned = oi_aligned and oi_timestamp_fresh

        cvd_start_ms = candle_end_ms - self.config.cvd_window_minutes * 60_000
        spot_window = self.flows[symbol]["spot"].window(
            cvd_start_ms, candle_end_ms, self.config.cvd_stale_after_seconds
        )
        swap_window = self.flows[symbol]["swap"].window(
            cvd_start_ms, candle_end_ms, self.config.cvd_stale_after_seconds
        )
        cvd_complete = spot_window.ready and swap_window.ready

        closes = [candle.close for candle in candles]
        ema_fast_values = ema(closes, self.config.strategy.ema_fast)
        ema_slow_values = ema(closes, self.config.strategy.ema_slow)
        macd_line, macd_signal, histogram = macd(
            closes,
            self.config.strategy.macd_fast,
            self.config.strategy.macd_slow,
            self.config.strategy.macd_signal,
        )
        atr_values = atr(candles, self.config.strategy.atr_period)
        divergence = detect_regular_macd_divergence(
            candles, macd_line, histogram, atr_values, self.config.strategy
        )
        previous = candles[-2]
        recent = candles[-21:-1]
        average_volume = sum(candle.volume for candle in recent) / len(recent)
        issues: list[str] = []
        if not cvd_complete:
            issues.append("CVD 暖機未完成、資料過期或 WebSocket 曾中斷")
        if not oi_aligned:
            issues.append("缺少同一 15 分鐘區間的連續 OI 樣本")
        snapshot = MarketSnapshot(
            symbol=symbol,
            timeframe=self.config.timeframe,
            candle_time_ms=latest.timestamp_ms,
            price=latest.close,
            ema_fast=ema_fast_values[-1],
            ema_slow=ema_slow_values[-1],
            macd=macd_line[-1],
            macd_signal=macd_signal[-1],
            macd_histogram=histogram[-1],
            previous_macd_histogram=histogram[-2],
            atr=atr_values[-1],
            oi_change_pct=oi_change,
            funding_rate=funding,
            flow=FlowSnapshot(
                spot_cvd_ratio=spot_window.ratio,
                swap_cvd_ratio=swap_window.ratio,
                spot_quote_volume=spot_window.quote_volume,
                swap_quote_volume=swap_window.quote_volume,
                ready=cvd_complete,
            ),
            previous_close=previous.close,
            volume_ratio=latest.volume / average_volume if average_volume else 0.0,
            divergence=divergence,
            data_quality=DataQuality(
                candles_confirmed=True,
                cvd_complete=cvd_complete,
                oi_aligned=oi_aligned,
                api_fresh=True,
                issues=tuple(issues),
            ),
        )
        signal = evaluate_signal(snapshot, self.config.strategy, self.config.risk)
        sent, not_sent_reason = await self._handle_signal(snapshot, signal)
        self.history.record(snapshot, signal, sent, not_sent_reason)
        self.last_processed_candle[symbol] = latest.timestamp_ms
        LOGGER.info(
            "%s candle=%s price=%s score=%+d sent=%s reason=%s",
            symbol,
            latest.timestamp_ms,
            latest.close,
            signal.score,
            sent,
            not_sent_reason,
        )

    async def _handle_signal(
        self, snapshot: MarketSnapshot, signal: Signal
    ) -> tuple[bool, str]:
        symbol = snapshot.symbol
        if signal.direction == Direction.NEUTRAL:
            self.pending_direction.pop(symbol, None)
            self.episode_alert.pop(symbol, None)
            return False, "總分位於 -3 到 +3，只記錄不推播"
        if not signal.eligible:
            self.pending_direction.pop(symbol, None)
            return False, self._gate_failure_reason(signal)
        if not self._confirmed(symbol, signal.direction, snapshot.candle_time_ms):
            return False, f"等待連續 {self.config.confirmation_scans} 根已收 K 線確認"
        if self._is_duplicate_divergence(snapshot, signal):
            return False, "同一組 MACD 背離樞紐已通知過"
        should_send, reason = self._should_send_update(symbol, signal)
        if not should_send:
            return False, reason
        try:
            await self.telegram.send(format_signal(signal, snapshot, self.config.risk))
        except Exception as exc:
            LOGGER.error("Telegram 發送 %s 失敗：%s", symbol, exc)
            return False, f"Telegram 發送失敗：{exc}"
        now = datetime.now(timezone.utc)
        self.last_alert[(symbol, signal.direction)] = now
        self.episode_alert[symbol] = (signal.direction, signal.score, signal.is_strong)
        if snapshot.divergence:
            self.notified_divergences.add(snapshot.divergence.key)
        return True, "已發送 Telegram"

    def _is_duplicate_divergence(
        self, snapshot: MarketSnapshot, signal: Signal
    ) -> bool:
        expected_score = 1 if signal.direction == Direction.LONG else -1
        return bool(
            snapshot.divergence
            and snapshot.divergence.score == expected_score
            and snapshot.divergence.key in self.notified_divergences
        )

    def _confirmed(self, symbol: str, direction: Direction, candle_time_ms: int) -> bool:
        previous = self.pending_direction.get(symbol)
        if previous and previous[0] == direction and previous[2] == candle_time_ms:
            return previous[1] >= self.config.confirmation_scans
        frame_ms = timeframe_to_ms(self.config.timeframe)
        if previous and previous[0] == direction and candle_time_ms - previous[2] == frame_ms:
            count = previous[1] + 1
        else:
            count = 1
        self.pending_direction[symbol] = (direction, count, candle_time_ms)
        return count >= self.config.confirmation_scans

    def _gate_failure_reason(self, signal: Signal) -> str:
        failures = list(signal.blocked_reasons)
        gates = signal.gates
        if gates:
            if not gates.direction_confirmed:
                failures.append("方向必要條件未通過")
            if not gates.funds_confirmed:
                failures.append("資金必要條件未通過")
            if not gates.independent_groups_confirmed:
                failures.append("同方向支持群組少於 3 個")
            if not gates.data_quality_confirmed:
                failures.append("資料品質必要條件未通過")
        return "；".join(dict.fromkeys(failures)) or "必要條件未通過"

    def _should_send_update(self, symbol: str, signal: Signal) -> tuple[bool, str]:
        episode = self.episode_alert.get(symbol)
        strong_upgrade = False
        if episode and episode[0] == signal.direction:
            improved = (
                signal.score > episode[1]
                if signal.direction == Direction.LONG
                else signal.score < episode[1]
            )
            strong_upgrade = not episode[2] and signal.is_strong
            if not improved and not strong_upgrade:
                return False, "方向未變且分數沒有改善，不重複推播"
        if strong_upgrade:
            return True, "普通訊號升級為強訊號"
        previous = self.last_alert.get((symbol, signal.direction))
        if previous is not None:
            cooldown = timedelta(minutes=self.config.alert_cooldown_minutes)
            if datetime.now(timezone.utc) - previous < cooldown:
                return False, "相同幣種與方向仍在冷卻時間"
        return True, "符合推播條件"


async def build_and_run(config: AppConfig) -> None:
    headers = {"User-Agent": "crypto-tg-monitor/0.2"}
    async with aiohttp.ClientSession(headers=headers) as session:
        notifier: NotificationClient
        if config.telegram_bot_token and config.telegram_chat_id:
            notifier = TelegramClient(
                session, config.telegram_bot_token, config.telegram_chat_id
            )
            LOGGER.info("通知輸出：Telegram")
        else:
            notifier = ConsoleClient()
            LOGGER.info("未設定 Telegram；通知直接輸出至 Codex／終端")
        service = MonitorService(config, OKXClient(session), notifier)
        await service.run()
