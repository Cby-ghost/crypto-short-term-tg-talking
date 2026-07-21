from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp
from dotenv import load_dotenv

from .config import AppConfig, load_config
from .history import SignalHistory
from .telegram import ConsoleClient, NotificationClient, TelegramClient


def _price(value: float) -> str:
    return f"{value:,.2f}" if value >= 1_000 else f"{value:,.4f}"


def _score_label(score: int, direction: str) -> str:
    if direction == "LONG":
        return "強多單" if score >= 5 else "多單"
    if direction == "SHORT":
        return "強空單" if score <= -5 else "空單"
    return "中性／未達推播門檻"


def format_four_hour_report(config: AppConfig, rows: list[dict[str, object]]) -> str:
    row_by_symbol = {str(row["symbol"]): row for row in rows}
    lines = [
        "🕓 <b>BTC／ETH／SOL 四小時盤面報告</b>",
        f"產生時間：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"主週期：{config.timeframe}",
    ]
    for symbol in config.symbols:
        row = row_by_symbol.get(symbol)
        lines.append("")
        if row is None:
            lines.extend(
                [
                    f"<b>{symbol}</b>",
                    "尚無完整監控資料；請確認監控服務持續執行並完成 CVD／OI 暖機。",
                ]
            )
            continue
        score = int(row["score"])
        direction = str(row["direction"])
        data_state = "完整" if bool(row["data_gate"]) else "未完整（不作交易通報）"
        lines.extend(
            [
                f"<b>{symbol}</b>｜{_score_label(score, direction)}｜分數 {score:+d}",
                f"最新收盤：<code>{_price(float(row['price']))}</code>｜資料：{data_state}",
                f"CVD（現貨／合約）：{float(row['spot_cvd_ratio']):+.2%}／{float(row['swap_cvd_ratio']):+.2%}",
                f"OI：{float(row['oi_change_pct']):+.2f}%｜資金費率：{float(row['funding_rate']):+.4%}",
                f"相對成交量：{float(row['volume_ratio']):.2f} 倍｜"
                f"MACD：{float(row['macd']):.6g}／柱 {float(row['macd_histogram']):.6g}",
                f"最近結果：{'已發送交易通報' if bool(row['telegram_sent']) else str(row['not_sent_reason'])}",
            ]
        )
    lines.extend(
        [
            "",
            "⚠️ 此報告僅整理條件式市場資料，不構成投資建議。",
        ]
    )
    return "\n".join(lines)


async def send_four_hour_report(config: AppConfig) -> None:
    rows = SignalHistory(config.signal_log_path, config.risk).latest_market_rows(config.symbols)
    report = format_four_hour_report(config, rows)
    async with aiohttp.ClientSession() as session:
        notifier: NotificationClient
        if config.telegram_bot_token and config.telegram_chat_id:
            notifier = TelegramClient(session, config.telegram_bot_token, config.telegram_chat_id)
        else:
            notifier = ConsoleClient()
        await notifier.send(report)


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(send_four_hour_report(load_config()))


if __name__ == "__main__":
    main()
