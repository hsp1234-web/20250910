# 一級交易商壓力儀表板技術調查報告

## 1. 總結

本報告旨在詳細解析「一級交易商壓力指標儀表板」頁面的後端實作，為未來重建一個新的、可靠的微服務提供完整的技術藍圖。

調查發現，該頁面的功能目前由一個**備份版本**的微服務 (`services/bond_data_service_backup/`) 提供支援。該服務雖然可以運作，但可能存在未知的問題，且與目前主流的 `v2` 版本架構不符。

一個關鍵的發現是：**後端服務不生成任何圖表圖片**。所有圖表都是由前端 JavaScript（使用 Plotly.js 函式庫）根據後端提供的純 JSON 資料動態繪製的。

## 2. 系統架構與請求流程

完整的請求鏈路如下：

1.  **前端 (src/static/js/primary_dealer_analysis.js)**
    *   使用者在頁面選擇日期並點擊「開始分析」。
    *   前端 JavaScript 為儀表板上的每一個圖表，向後端發起一個 GET 請求。
    *   **請求端點格式**: `/api/bond_service/data/{indicator_id}`
    *   **範例**: `/api/bond_service/data/sofr`, `/api/bond_service/data/stress_index`

2.  **API Gateway (src/api/api_server.py)**
    *   接收到請求。
    *   根據路由規則，將所有符合 `/api/bond_service/` 前綴的請求轉發給 `bond_service_proxy.py` 處理。

3.  **代理 (src/api/routes/bond_service_proxy.py)**
    *   此代理讀取 `/tmp/service_registry.json` 檔案，找到 `bond_data_service` 微服務實際運行的埠號。
    *   將請求完整轉發到對應的微服務上。例如，將 `/data/sofr` 請求轉發到 `http://127.0.0.1:{port}/data/sofr`。

4.  **微服務 (services/bond_data_service_backup/main.py)**
    *   微服務的 `/data/{chart_id}` 端點接收到請求。
    *   此端點是整個資料生成的核心，它會觸發後續的所有計算和資料獲取。
    *   最終，它會從計算出的大量指標中，篩選出該 `chart_id` 所需的欄位，並以 JSON 陣列的形式回傳給前端。

## 3. 後端 API 端點規格

為重建此服務，後端必須實作以下核心端點：

*   **端點**: `GET /data/{chart_id}`
*   **路徑參數**:
    *   `chart_id` (string): 代表前端圖表的唯一識別碼。例如 `sofr`, `stress_index`, `vix` 等。
*   **查詢參數**:
    *   `start_date` (string, YYYY-MM-DD): 數據範圍的開始日期。
    *   `end_date` (string, YYYY-MM-DD): 數據範圍的結束日期。
*   **成功回應 (200 OK)**:
    *   **內容**: 一個 JSON 陣列，每個物件代表一個時間點的數據。
    *   **範例 (`/data/stress_index_macd`)**:
        ```json
        [
          {
            "date": "2023-01-01",
            "dealer_stress_index": 55.5,
            "macd_line": 1.2,
            "macd_signal_line": 1.1,
            "macd_hist": 0.1
          },
          {
            "date": "2023-01-02",
            "dealer_stress_index": 56.1,
            "macd_line": 1.3,
            "macd_signal_line": 1.15,
            "macd_hist": 0.15
          }
        ]
        ```
*   **其他必要端點**:
    *   `GET /health`: 一個簡單的健康檢查端點，返回 `{"status": "ok"}` 即可。

## 4. 核心指標計算邏輯 (`stress_index_calculator.py`)

所有指標的計算都圍繞 `calculate_full_metrics` 這個核心函式展開。

1.  **獲取基礎數據**: 從 `DataManager` 獲取所有原始數據序列。
2.  **計算衍生指標**:
    *   `spread_10y2y` = `DGS10` - `DGS2`
    *   `sofr_dev` = `SOFR` - `SOFR` 的 60 日移動平均
    *   `pos_res_ratio` = `dealer_net_positions` / `WRESBAL`
3.  **滾動百分位排名 (標準化)**:
    *   為以下每個成分計算其在過去 252 個交易日的滾動百分位排名 (0 到 1)。
    *   `sofr_dev`
    *   `spread_10y2y` (反向指標, 使用 `1 - rank`)
    *   `us_high_yield_spread` (HYG 價格的反向指標, 使用 `1 - rank`)
    *   `dealer_net_positions`
    *   `vix`
    *   `pos_res_ratio`
4.  **加權合成壓力指數**:
    *   使用以下權重將標準化後的指標加權求和：
        ```
        {
            'sofr_dev': 0.25,
            'spread_inv': 0.10,
            'hys_inv': 0.10,
            'gross_pos': 0.05,
            'move': 0.25,      // 注意：MOVE 指數目前未被獲取，此權重實際未生效
            'vix': 0.15,
            'pos_res_ratio': 0.10
        }
        ```
    *   **注意**: 權重會根據實際獲取到的數據進行正規化。
5.  **平滑與格式化**:
    *   對合成指數進行 5 日移動平均。
    *   將結果乘以 100，並裁剪到 [0, 100] 區間。
6.  **計算 MACD**:
    *   基於最終的壓力指數，計算其 12-26-9 MACD 指標。

## 5. 原始數據來源清單 (`data_fetchers`)

重建服務時，必須能夠從以下來源獲取數據。建議實作一個資料庫快取層以提高效能。

| 內部指標名稱 | 數據來源 | 序列/Ticker | 說明 |
| --- | --- | --- | --- |
| `sofr` | FRED API | `SOFR` | 擔保隔夜融資利率 |
| `dgs10` | FRED API | `DGS10` | 10 年期美國公債殖利率 |
| `dgs2` | FRED API | `DGS2` | 2 年期美國公債殖利率 |
| `vix` | FRED API | `VIXCLS` | CBOE 波動率指數 (恐慌指數) |
| `wresbal` | FRED API | `WRESBAL` | 聯準會準備金餘額 (週頻) |
| `rrp` | FRED API | `RRPONTSYD` | 隔夜逆回購協議 (Reverse Repo) |
| `us_high_yield_spread` | Yahoo Finance | `HYG` | 高收益債券 ETF (收盤價) |
| `dealer_net_positions` | NY Fed (Excel) | (多個 URL) | 一級交易商淨部位 (週頻) |
| `dealer_long_term_positions` | NY Fed (Excel) | (多個 URL) | 一級交易商長天期部位 (週頻) |
| `dealer_short_term_positions`| NY Fed (Excel) | (多個 URL) | 一級交易商短天期部位 (週頻) |
| `move` | - | - | MOVE 指數 (目前未實作抓取器) |

**NY Fed Excel 檔案 URL 列表:**
```
https://markets.newyorkfed.org/api/pd/get/SBN2024/timeseries/PDPOSGSC-L2_PDPOSGSC-G2L3_PDPOSGSC-G3L6_PDPOSGSC-G6L7_PDPOSGSC-G7L11_PDPOSGSC-G11L21_PDPOSGSC-G21.xlsx
https://markets.newyorkfed.org/api/pd/get/SBN2022/timeseries/PDPOSGSC-L2_PDPOSGSC-G2L3_PDPOSGSC-G3L6_PDPOSGSC-G6L7_PDPOSGSC-G7L11_PDPOSGSC-G11L21_PDPOSGSC-G21.xlsx
https://markets.newyorkfed.org/api/pd/get/SBN2015/timeseries/PDPOSGSC-L2_PDPOSGSC-G2L3_PDPOSGSC-G3L6_PDPOSGSC-G6L7_PDPOSGSC-G7L11_PDPOSGSC-G11.xlsx
https.://markets.newyorkfed.org/api/pd/get/SBN2013/timeseries/PDPOSGSC-L2_PDPOSGSC-G2L3_PDPOSGSC-G3L6_PDPOSGSC-G6L7_PDPOSGSC-G7L11_PDPOSGSC-G11.xlsx
https://markets.newyorkfed.org/api/pd/get/SBP2013/timeseries/PDPUSGCS3LNOP_PDPUSGCS36NOP_PDPUSGCS611NOP_PDPUSGCSM11NOP.xlsx
https://markets.newyorkfed.org/api/pd/get/SBP2001/timeseries/PDPUSGCS5LNOP_PDPUSGCS5MNOP.xlsx
```

---

## 6. v2.1 版本功能異常調查分析報告 (2025-10-23)

### 6.1. 根本原因分析

經過對 v2.1 版本 (`services/bond_data_service/`) 的程式碼、啟動日誌及前端邏輯的詳細分析，已確認功能異常的根本原因是一個典型的**「冷啟動」競賽條件 (Race Condition)** 問題，由以下四個因素疊加造成：

1.  **協調器延遲啟動**:
    *   `orchestrator.py` 在主系統就緒後，會等待 15 秒才開始啟動 `bond_data_service`。這為問題的發生埋下了伏筆。

2.  **首次啟動的快取缺失**:
    *   服務在首次啟動時，其本地資料庫快取 (`bond_data.sqlite3`) 是空的。
    *   `repository.py` 中的 `get_series` 函式在快取未命中時，會觸發從外部網路來源（FRED, Yahoo Finance, NY Fed）抓取即時資料。

3.  **同步阻塞的資料抓取**:
    *   服務啟動後，背景任務 `periodic_data_updater` 會呼叫 `service.py` 中的 `check_for_updates` 函式，進而觸發對**所有**必要金融數據的抓取。
    *   這個資料抓取過程是**同步且阻塞**的，意味著它會完全佔用服務的主執行緒，直到所有網路請求完成。

4.  **前端健康檢查失敗**:
    *   前端 `primary_dealer_analysis.js` 在使用者點擊「開始分析」後，會立即開始每 2 秒輪詢一次 API 閘道的 `/api/bond_service/health` 端點。
    *   由於後端 `bond_data_service` 的主執行緒被資料抓取阻塞，其 Uvicorn 伺服器雖然可能已啟動，但無法回應任何傳入的 HTTP 請求。
    *   API 閘道的代理請求因此失敗（日誌中顯示為 `500 Internal Server Error`），導致前端永遠卡在「正在等待後端服務啟動...」的狀態，無法進入下一步的圖表載入流程。

**結論**: 問題的核心是後端服務的**啟動流程設計**。它在能夠回應外部請求之前，就先執行了一個耗時極長的、阻塞性的資料初始化任務，導致其在關鍵的啟動窗口期處於「假死」狀態，無法通過前端的健康檢查。

### 6.2. 解決方案建議

以下提出三種可能的解決方案方向，由淺入深，供您決策。**在獲得您的明確授權前，不會實作任何方案。**

#### 方案 A：優化啟動流程 (非阻塞式初始化 - 推薦)

*   **說明**:
    修改 `services/bond_data_service/main.py` 的 `lifespan` 函式。讓 FastAPI 應用程式立即啟動並能夠回應請求，特別是 `/health` 端點。將耗時的資料抓取任務完全放入一個獨立的、非阻塞的背景執行緒中執行。在資料尚未準備好時，圖表數據端點 (`/data/{chart_id}`) 可以回傳一個明確的「正在初始化」狀態或空的數據集。
*   **優點**:
    *   從根本上解決了問題，確保服務在啟動後能立刻回應，通過健康檢查。
    *   使用者體驗更佳，前端可以明確知道服務是在載入中，而不是卡在一個模糊的錯誤狀態。
    *   符合現代微服務快速啟動、非阻塞的設計模式。
*   **缺點**:
    *   需要對服務的啟動邏輯進行較大範圍的重構，使其完全非同步化。

#### 方案 B：在健康檢查中增加「就緒」狀態

*   **說明**:
    修改 `/health` 端點的邏輯。增加一個全域狀態變數，例如 `IS_DATA_READY`，預設為 `False`。
    1.  當 `/health` 被請求時，如果 `IS_DATA_READY` 是 `False`，則回傳 `{"status": "initializing"}`，但 HTTP 狀態碼依然是 `200 OK`。
    2.  當背景的資料抓取任務完成後，將 `IS_DATA_READY` 設為 `True`。
    3.  此後，`/health` 端點回傳 `{"status": "ok"}`。
    同時，需要修改前端的 `checkServiceHealth` 函式，使其不僅檢查 HTTP `200` 狀態，還要檢查回傳 JSON 中的 `status` 欄位是否為 `"ok"`。
*   **優點**:
    *   改動範圍較方案 A 小，對現有啟動邏輯的侵入性較低。
    *   為前端提供了比單純的 `500` 錯誤更清晰的服務狀態信號。
*   **缺點**:
    *   使用者仍然需要等待漫長的冷啟動過程。
    *   需要同時修改後端和前端的程式碼。

#### 方案 C：延長前端的等待時間 (治標不治本)

*   **說明**:
    此方案最為簡單，直接修改 `primary_dealer_analysis.js` 中的 `waitForServiceReady` 函式，將輪詢的間隔從 `2000` 毫秒（2秒）增加到一個更長的值，例如 `10000` 毫秒（10秒）。
*   **優點**:
    *   實作極為簡單，只需修改一行前端程式碼。
*   **缺點**:
    *   **完全沒有解決後端啟動緩慢的根本問題**。這只是一個「賭博式」的修復，賭後端能在新的、更長的超時時間內完成啟動。
    *   如果未來資料抓取時間變得更長，問題會再次出現。
    *   使用者在點擊按鈕後，頁面會長時間處於無反應的等待狀態，使用者體驗極差。