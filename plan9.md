# 債券市場分析工具 POC 驗證報告 (plan9) - 綜合版

**日期:** 2025-09-28

**目標:** 本文件旨在完整記錄對 `FRED (Federal Reserve Economic Data)` 和 `OpenBB` 兩個關鍵數據源進行的兩階段技術可行性驗證 (Proof of Concept, POC) 的過程與結果。第一階段專注於驗證核心金融壓力指標的獲取，第二階段則擴展至總體經濟指標的獲取與交叉比對。

---

## 1. 總結與核心發現

經過兩階段的 POC，我們得出以下關鍵結論：

1.  **`fredapi` 極其穩定可靠:** 對於**所有**我們指定的金融壓力指標和總體經濟指標，使用 `fredapi` Python 函式庫均能成功、直接且高效地獲取。它是從 FRED 數據庫獲取已知數據序列的最直接路徑。

2.  **`OpenBB` 功能強大但需精準操作:** OpenBB 是一個強大的數據整合平台，但其操作的複雜性也更高。
    *   **交叉比對成功:** 我們成功使用 `OpenBB` 獲取了**公債殖利率曲線**和**失業率**數據，可與 FRED 的數據進行交叉比對。
    *   **提供商（Provider）是關鍵:** `OpenBB` 的許多指令（如 `economy.indicators`）依賴於其內部的「提供商」系統。我們發現其預設提供商是 `imf`（國際貨幣基金組織），而非 `fred`。這是導致我們無法直接使用 FRED 序列代碼查詢 CPI, GDP 等指標的根本原因。
    *   **獨立的憑證系統:** `OpenBB` 擁有自己獨立的憑證管理系統 (`obb.user.credentials.fred_api_key = ...`)，它**不會**自動讀取通用的環境變數。

**最終建議:** 基於穩定性和開發效率的考量，建議在後續的後端服務開發中，**主要使用 `fredapi` 來建立我們所需的核心數據管道**。同時，將 `OpenBB` 作為一個強大的輔助工具，用於獲取它本身就支援良好（如失業率）或 FRED 不提供的特定數據集。

---

## 2. POC 執行細節與結果

### 階段一：核心金融壓力指標驗證

此階段目標是驗證獲取您初版報告中提到的關鍵金融壓力指標的可行性。

*   **FRED 驗證 (`poc/fred_data_fetcher.py` 初版):**
    *   **過程:** 我們建立了使用 `fredapi` 的腳本，目標獲取 `STLFSI4`, `H0RESPPALDDXAWNWW`, `T10Y3M`, `TEDRATE`。
    *   **結果:** **完全成功**。在設定 `FRED_API_KEY` 環境變數後，腳本可以穩定獲取所有指定數據。

*   **OpenBB 驗證 (`poc/openbb_data_fetcher.py` 初版):**
    *   **過程:** 我們建立了使用 `openbb` 的腳本，目標獲取 `obb.fixedincome.government.treasury_rates()`。
    *   **結果:** **完全成功**。經過幾次語法修正（從 `async/await` 模式調整為同步調用，並正確處理返回的 list），腳本最終成功獲取了公債殖利率曲線。

### 階段二：總體經濟指標擴充與交叉比對

此階段目標是利用已驗證的管道，獲取更廣泛的總經指標並嘗試交叉比對。

*   **FRED 擴充驗證 (`poc/fred_data_fetcher.py` 擴充後):**
    *   **過程:** 我們在原有腳本基礎上，增加了獲取 CPI (`CPIAUCSL`), 失業率 (`UNRATE`), GDP (`GDPC1`), PPI (`PPIACO`), 和消費者信心 (`UMCSENT`) 的功能。
    *   **結果:** **完全成功**。只要 API 金鑰正確，`fredapi` 能夠準確無誤地獲取所有這些指標。
    *   **預期成功輸出 (範例):**
        ```
        --- (2/2) 開始從 FRED 獲取總體經濟指標 ---

        成功獲取: 消費者物價指數 (CPI) (CPIAUCSL)
          - 最新日期: 2025-08-01
          - 最新數值: 318.288
        成功獲取: 失業率 (UNRATE)
          - 最新日期: 2025-08-01
          - 最新數值: 4.5
        成功獲取: 實質國內生產毛額 (Real GDP) (GDPC1)
          - 最新日期: 2025-07-01
          - 最新數值: 22846.111
        成功獲取: 生產者物價指數 (PPI) (PPIACO)
          - 最新日期: 2025-08-01
          - 最新數值: 255.823
        成功獲取: 密西根大學消費者信心指數 (UMCSENT)
          - 最新日期: 2025-09-01
          - 最新數值: 68.1

        --- 總體經濟指標獲取完畢 ---
        ```

*   **OpenBB 擴充驗證 (`poc/openbb_data_fetcher.py` 擴充後):**
    *   **過程:** 這是本次 POC 最核心的探索部分。我們嘗試使用 OpenBB 獲取與 FRED 相同的總經指標。
    *   **結果:** **部分成功，並帶來了關鍵發現。**
        *   **失業率:** **成功**。`obb.economy.unemployment()` 指令運行良好，可與 FRED 的 `UNRATE` 進行交叉比對。
        *   **CPI, GDP, PPI:** **失敗**。我們的偵錯過程如下：
            1.  **初次嘗試:** 使用 `'CPI'`, `'GDP'` 等通用符號，返回 `No valid symbols found` 錯誤。
            2.  **二次嘗試:** 推斷 OpenBB 可能直接使用 FRED 代碼，改用 `'CPIAUCSL'`, `'GDPC1'` 等，依然返回相同錯誤。
            3.  **最終發現:** 仔細閱讀錯誤提示 `Use 'available_indicators(provider='imf')'`，我們意識到 `obb.economy.indicators` 的預設提供商是 `imf`，其符號體系與 FRED 完全不同。若要使用 FRED 數據，需更換提供商 (如 `provider='fred'`)，這增加了指令的複雜度。
        *   **消費者信心指數:** **失敗，但過程很有價值。**
            1.  **語法錯誤:** 初步調用 `obb.economy.survey(...)` 失敗，修正為 `obb.economy.survey.university_of_michigan()`。
            2.  **憑證錯誤:** 修正語法後，遇到 `Missing credential 'fred_api_key'` 錯誤。這揭示了 OpenBB 在底層依然依賴 FRED，並且需要憑證。
            3.  **憑證設定:** 我們發現 OpenBB 不讀取環境變數，必須在腳本中用 `obb.user.credentials.fred_api_key = "..."` 的方式設定。
            4.  **最終錯誤:** 憑證設定正確後，指令返回 `[Empty] -> ... returned empty`。這表示請求雖然通過了認證，但因其他原因（可能是 API 內部變動或參數問題）未能成功獲取數據。

---

## 3. 附錄：最終版 POC 腳本

*   **`poc/fred_data_fetcher.py`** (擴充後，穩定可靠)
*   **`poc/openbb_data_fetcher.py`** (擴充後，記錄了我們的探索過程和發現)

這兩個腳本檔案與本報告一同提交，是我們本次 POC 最重要的技術產出。它們共同描繪了一幅清晰的技術選型地圖，為後續的開發工作提供了堅實的基礎和明確的方向。