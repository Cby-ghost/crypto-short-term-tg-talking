from __future__ import annotations

import html
import re
from typing import Protocol

import aiohttp

from .config import RiskConfig
from .models import Direction, DivergenceKind, MarketSnapshot, Signal


class NotificationClient(Protocol):
    async def send(self, text: str) -> None: ...


class ConsoleClient:
    async def send(self, text: str) -> None:
        plain_text = html.unescape(re.sub(r"<[^>]+>", "", text))
        print(plain_text, flush=True)


class TelegramClient:
    def __init__(self, session: aiohttp.ClientSession, token: str, chat_id: str) -> None:
        self.session = session
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id

    async def send(self, text: str) -> None:
        async with self.session.post(
            f"{self.base_url}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            payload = await response.json()
            if not response.ok or not payload.get("ok"):
                raise RuntimeError(f"Telegram 發送失敗：{payload.get('description', response.status)}")


def _price(value: float) -> str:
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:,.4f}"
    return f"{value:.8f}"


def _gate_line(passed: bool, text: str) -> str:
    return f"{'✅' if passed else '❌'} {html.escape(text)}"


def format_signal(signal: Signal, snapshot: MarketSnapshot, risk: RiskConfig) -> str:
    icon = "🟢" if signal.direction == Direction.LONG else "🔴"
    sign = 1 if signal.direction == Direction.LONG else -1
    reason_lines = "\n".join(
        f"{vote.score:+d} {html.escape(vote.reason)}"
        for vote in signal.votes
        if vote.score == sign
    ) or "無"
    risk_lines = "\n".join(f"• {html.escape(item)}" for item in signal.warnings) or "• 無明顯反向投票"
    gates = signal.gates
    gate_lines = "\n".join(
        (
            _gate_line(bool(gates and gates.direction_confirmed), "EMA 或已確認 MACD 背離方向確認通過"),
            _gate_line(bool(gates and gates.funds_confirmed), "資金確認通過"),
            _gate_line(
                bool(gates and gates.independent_groups_confirmed),
                "至少 3 個獨立群組支持同方向",
            ),
            _gate_line(bool(gates and gates.data_quality_confirmed), "資料完整且時間一致"),
        )
    )
    divergence_summary = "無有效背離"
    if snapshot.divergence:
        item = snapshot.divergence
        label = "底背離" if item.kind == DivergenceKind.BULLISH else "頂背離"
        divergence_summary = (
            f"{label}，已確認，剩餘有效 {item.bars_remaining} 根 K 線；"
            f"價格 {_price(item.first_price)}→{_price(item.second_price)}，"
            f"MACD {item.first_macd:.6g}→{item.second_macd:.6g}"
        )
    size_line = ""
    if signal.position_size_base is not None:
        size_line = f"\n估算部位：<code>{signal.position_size_base:.6f}</code> 幣"
    strength = "強訊號" if signal.is_strong else "普通訊號"
    return (
        f"{icon} <b>{html.escape(signal.symbol)} {signal.notification_title}</b>\n"
        f"週期：{html.escape(snapshot.timeframe)}\n"
        f"總分：<b>{signal.score:+d}</b>｜{strength}\n\n"
        f"<b>【{signal.notification_title}原因】</b>\n{reason_lines}\n\n"
        f"<b>【必要條件】</b>\n{gate_lines}\n\n"
        f"<b>【風險與反對理由】</b>\n{risk_lines}\n\n"
        f"進場參考：<code>{_price(signal.entry)}</code>\n"
        f"停損參考：<code>{_price(signal.stop_loss)}</code>\n"
        f"止盈：<code>{_price(signal.take_profit)}</code>{size_line}\n"
        f"價格距離盈虧比：1:{signal.price_rr:.2g}\n"
        f"扣除成本後盈虧比：1:{signal.cost_adjusted_rr:.2f}"
        f"（單邊手續費 {risk.fee_rate_pct:.3f}%＋滑價 {risk.slippage_pct:.3f}%）\n\n"
        f"<b>【訊號失效】</b>\n{html.escape(signal.invalidation)}\n\n"
        f"CVD（現貨／合約）：{snapshot.flow.spot_cvd_ratio:+.2%}／"
        f"{snapshot.flow.swap_cvd_ratio:+.2%}\n"
        f"OI 變化：{snapshot.oi_change_pct:+.2f}%\n"
        f"資金費率：{snapshot.funding_rate:+.4%}\n"
        f"相對成交量：{snapshot.volume_ratio:.2f} 倍\n"
        f"MACD：線 {snapshot.macd:.6g}｜訊號 {snapshot.macd_signal:.6g}｜"
        f"柱 {snapshot.macd_histogram:.6g}\n"
        f"MACD 背離：{html.escape(divergence_summary)}\n\n"
        "⚠️ 這是條件式短線通報，不保證獲利，下單前仍需自行確認風險。"
    )
