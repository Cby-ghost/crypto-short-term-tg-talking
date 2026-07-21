# WORK LOG

## 2026-07-20 — 15m 主訊號與 1H 趨勢權重

- 模式：深度模式（交易評分邏輯）。
- 決策：主訊號維持 15m；額外讀取 1H 已收 K 線，以 EMA 20/50 判斷多空，多頭 +2、空頭 -2。
- 實作：新增 `trend_timeframe`、`higher_timeframe_weight`、高週期快慢 EMA 欄位及通知／CSV 投票內容；總分設定上限隨權重調整。
- 設定：建立本機 `config.yaml`，主週期 `15m`、趨勢週期 `1H`、權重 `2`。
- 測試：新增 1H 權重正反向測試，以及服務同時請求 15m／1H 的整合測試。
- 驗證：`.venv\\Scripts\\python.exe -m pytest -q`，12 passed。
- 環境：專案目錄沒有 `.git`，因此無法執行 `git diff --check`；修改範圍以明確相關檔案控制。

## 2026-07-20 — 15m 短線通報規格重構

- 模式：深度模式（交易評分、資料一致性、風控與通知）。
- 規格決策：最新附件覆蓋上一版 1H 權重；正式執行路徑改為純 15m 已收 K 線，普通投票僅 `±1/0`，基礎群組分數封頂為 `±6`。
- 精簡：移除舊震盪投票與 20 根突破投票，未加入替代震盪指標。
- 背離：新增 Regular MACD 頂／底背離、左右樞紐確認、間隔／ATR／MACD 差異門檻、3 根有效期、衝突處理與穩定防重複鍵。
- 評分：MACD 群組封頂 `±1`、資金流封頂 `±2`；資金費率僅降低擁擠方向；門檻維持 `±4`，強訊號 `±5`。
- 必要條件：方向、資金、至少三個群組、資料品質全部通過才可推播。
- 資料：成交來源改為 OKX `trades-all` business WebSocket；斷線自動重連並重置 CVD 暖機。OI 只在新 15m 已收 K 出現時取樣，與相鄰收盤樣本比較。
- 防洗版：同一根 K 不重複確認；要求連續已收 K；保留方向冷卻、分數改善與普通升強通知規則；同一背離樞紐只通知一次。
- 風控／通知：只保留一個 1:1 止盈，顯示成本後盈虧比、實際原因、反對理由、必要條件、失效條件與背離數值。
- 紀錄：改用 SQLite 保存投票、群組、背離、必要條件、推播結果、成本，以及後續 1/4/8/16 根報酬與 MFE/MAE。
- 官方契約：依 OKX API v5 的 `trades-all` business WebSocket 與已確認 K 線欄位實作。
- 驗證：`python -m compileall -q src tests` 通過；`pytest -q` 為 24 passed。
- 已知限制：公開 OI 以新 K 線出現時的快照近似 15m 收盤 OI；WebSocket 斷線期間成交無法補回，因此採整窗重新暖機。

## 2026-07-20 — Codex／終端直接通知

- 模式：標準模式（通知輸出與啟動設定）。
- 決策：OKX 公開行情不需要私人 API；未設定 Telegram 時改用 `ConsoleClient`，讓 Codex 可直接讀取多空通報。
- 相容性：Telegram 保留為可選輸出；Token 與 Chat ID 同時存在時才啟用。
- 啟動：移除 Docker Compose 對 `.env` 的硬依賴，空白 Telegram 設定不再阻止 `load_config`。
- 文件：補充 Codex Scheduled task、本機長期運行、CVD 暖機與 OI 樣本需求。
- 驗證：新增無 Telegram 設定與純文字輸出測試；完整測試為 26 passed。

## 2026-07-21 — BTC／ETH／SOL 四小時盤面報告

- 新增 `crypto-monitor-report` 指令：從既有 SQLite 訊號紀錄讀取 BTC、ETH、SOL 最新 15 分鐘資料，輸出分數、多空狀態、資料完整度、CVD、OI、資金費率、相對成交量、MACD 與最近通報結果。
- SQLite 紀錄增加上述原始市場欄位，並在既有資料庫啟動時以安全 migration 補齊欄位；不影響既有結果回填。
- 報告沿用既有通知出口：兩項 Telegram 憑證齊全時發 Telegram，否則輸出到 Codex／終端；不會下單或修改策略。
- 新增報告格式與最新資料列測試；`python -m compileall -q src tests` 通過，`pytest -q` 為 28 passed。
- 已建立 Codex 本機排程「BTC／ETH／SOL 四小時盤面報告」，每天台北時間 00:00、04:00、08:00、12:00、16:00、20:00 執行報告指令。
