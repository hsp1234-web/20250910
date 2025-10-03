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