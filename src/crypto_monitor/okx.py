from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import aiohttp

from .models import Candle, MarketTrade, OpenInterestSnapshot

LOGGER = logging.getLogger(__name__)


class OKXError(RuntimeError):
    pass


class OKXClient:
    BASE_URL = "https://www.okx.com"
    BUSINESS_WS_URL = "wss://ws.okx.com:8443/ws/v5/business"

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def _get(self, path: str, params: dict[str, str]) -> list[Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with self.session.get(
                    f"{self.BASE_URL}{path}", params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    response.raise_for_status()
                    payload = await response.json()
                    if payload.get("code") != "0":
                        raise OKXError(f"OKX {payload.get('code')}: {payload.get('msg')}")
                    return payload.get("data", [])
            except (aiohttp.ClientError, asyncio.TimeoutError, OKXError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
        raise OKXError(f"OKX 請求失敗：{last_error}")

    async def candles(self, symbol: str, bar: str, limit: int = 200) -> list[Candle]:
        rows = await self._get(
            "/api/v5/market/candles",
            {"instId": symbol, "bar": bar, "limit": str(min(limit, 300))},
        )
        candles = [
            Candle(
                timestamp_ms=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in rows
            if len(row) >= 9 and row[8] == "1"
        ]
        return sorted(candles, key=lambda item: item.timestamp_ms)

    async def open_interest(self, symbol: str) -> OpenInterestSnapshot:
        rows = await self._get(
            "/api/v5/public/open-interest", {"instType": "SWAP", "instId": symbol}
        )
        if not rows:
            raise OKXError(f"{symbol} 沒有 OI 資料")
        row = rows[0]
        return OpenInterestSnapshot(
            value=float(row.get("oiUsd") or row["oi"]),
            timestamp_ms=int(row["ts"]),
        )

    async def funding_rate(self, symbol: str) -> float:
        rows = await self._get("/api/v5/public/funding-rate", {"instId": symbol})
        if not rows:
            raise OKXError(f"{symbol} 沒有資金費率資料")
        return float(rows[0]["fundingRate"])

    async def stream_all_trades(
        self,
        instruments: tuple[str, ...],
        on_trade: Callable[[str, MarketTrade], None],
        on_state_change: Callable[[bool], None],
    ) -> None:
        retry_seconds = 1
        while True:
            try:
                async with self.session.ws_connect(
                    self.BUSINESS_WS_URL,
                    heartbeat=20,
                    receive_timeout=45,
                    timeout=aiohttp.ClientWSTimeout(ws_close=10),
                ) as websocket:
                    await websocket.send_json(
                        {
                            "id": "crypto-monitor-trades",
                            "op": "subscribe",
                            "args": [
                                {"channel": "trades-all", "instId": instrument}
                                for instrument in instruments
                            ],
                        }
                    )
                    on_state_change(True)
                    retry_seconds = 1
                    async for message in websocket:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            payload = message.json()
                            if payload.get("event") == "error":
                                raise OKXError(
                                    f"WebSocket 訂閱失敗：{payload.get('code')} {payload.get('msg')}"
                                )
                            instrument = payload.get("arg", {}).get("instId")
                            for row in payload.get("data", []):
                                if not instrument:
                                    continue
                                on_trade(
                                    instrument,
                                    MarketTrade(
                                        trade_id=str(row["tradeId"]),
                                        timestamp_ms=int(row["ts"]),
                                        price=float(row["px"]),
                                        size=float(row["sz"]),
                                        side=str(row["side"]),
                                    ),
                                )
                        elif message.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            raise OKXError("OKX trades-all WebSocket 已關閉")
            except asyncio.CancelledError:
                on_state_change(False)
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, OKXError) as exc:
                LOGGER.warning("OKX trades-all WebSocket 中斷：%s；%d 秒後重連", exc, retry_seconds)
            finally:
                on_state_change(False)
            await asyncio.sleep(retry_seconds)
            retry_seconds = min(retry_seconds * 2, 30)


def spot_symbol(swap_symbol: str) -> str:
    if not swap_symbol.endswith("-SWAP"):
        raise ValueError(f"不是永續合約代號：{swap_symbol}")
    return swap_symbol.removesuffix("-SWAP")
