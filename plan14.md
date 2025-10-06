# 計畫：建立文件智慧處理微服務 (plan14.md)

## 1. 核心原則與開發目標

### 1.1. 核心設計原則：本地 AI，完全獨立

本專案將遵循以下核心原則，建立一個全新的 `document_processor_service` 微服務：

*   **本地 AI 分析**：所有文件的智慧分析工作，都必須由一個在本地伺服器、純 CPU 環境下運行的輕量級語言模型完成。**嚴格禁止使用任何需要外部網路存取的 AI 服務 (如 Google Gemini)**。
*   **完全獨立解耦**：此服務將擁有自己的程式碼、執行環境、專屬資料庫 (`document_processor.sqlite3`) 與獨立的測試案例，與所有現存的系統徹底解耦，確保對主系統**零影響**。
*   **非同步處理**：考慮到文件處理（下載、分析）可能是耗時操作，所有核心處理流程都將設計為非同步任務，以確保 API 能快速回應。

### 1.2. 開發目標

本計畫旨在整合並重構現有的工具模組，建立一個完整的、自動化的文件處理流程。此流程將接收一個網址，最終將網址背後文件的深度分析結果，以結構化的形式儲存到資料庫中。

開發將遵循「後端優先、分段開發、可被測試」的策略。

## 2. 文字流程圖 (Workflow)

新服務的內部工作流程如下：

```
[接收 API 請求: /api/process_document]
(原始 URL: "http://...")
       |
       v
[1. 下載模組] (呼叫 universal_downloader)
(產出: 本地文件路徑, e.g., "/tmp/file.pdf")
       |
       v
[2. 拆解模組] (呼叫 content_extractor)
(產出: 純文字內容 "...")
       |
       v
[3. 分析模組 (本地 AI)]
   |
   +--> [3a. 建構提示詞 (Prompt)]
   |    (指示 AI 根據文字，生成包含**五個**指定欄位的 JSON)
   |
   +--> [3b. 呼叫 llm_service]
   |    (將提示詞與文字發送至本地 AI 模型)
   |
   +--> [3c. 接收並驗證 AI 產出的 JSON]
   (產出: 結構化資料 { "summary": ..., "stock_id": ... })
       |
       v
[4. 保存模組] (寫入專屬資料庫)
(將 AI 分析結果與**原始 URL**一同存入 document_processor.sqlite3 的 `processed_documents` 表)
       |
       v
[返回成功訊息]
(API 回應: "文件已加入處理佇列")
```

## 3. 輸出欄位定義

本地 AI 分析後，必須產出包含以下六個欄位的結構化資料：

1.  **內容大意 (summary)**: `TEXT` (50-100字)
2.  **股票代號 (stock_id)**: `TEXT` (若無則為空值)
3.  **使用策略 (strategy)**: `TEXT` (選項: `看多`, `看空`, `多策略`, `無法判斷`, `空值`)
4.  **整體品質 (quality_score)**: `INTEGER` (範圍 1-10)
5.  **是否為交易相關 (is_trade_related)**: `TEXT` (選項: `是`, `否`, `空值`)
6.  **原始文件URL (source_url)**: `TEXT` (記錄來源)
    *   **資料來源備註**：此欄位值**必須**直接來自 API 請求中未經處理的原始 URL，**嚴禁**由 AI 模型生成或修改，以確保資料來源的絕對準確性。

## 4. 後端開發階段

1.  **建立微服務基礎架構**
    *   建立新目錄 `services/document_processor_service/`。
    *   在其中建立 `main.py`, `api_routes.py`, `processor.py` (核心處理流程), `repository.py`, `requirements.txt`。

2.  **整合現有工具模組**
    *   在 `processor.py` 中，匯入並呼叫 `src/tools/universal_downloader.py` 和 `src/tools/content_extractor.py` 的功能，完成流程圖中的步驟 1 和 2。

3.  **開發本地 AI 分析模組**
    *   在 `processor.py` 中，設計一個強健的提示詞 (Prompt) 工程函式。
    *   此函式需能將提取出的文件文字，包裝成一個能指導 `llm_service` (使用如 `gemma2:2b` 的本地模型) 產出符合**第 3 節**所定義的**前五個欄位**的 JSON 格式的指令。
    *   實作呼叫 `llm_service` 的 `/generate` 端點的邏輯。

4.  **建立專屬資料庫與倉儲層**
    *   在 `repository.py` 中，定義一個 `initialize_database` 函式，用於在 `document_processor.sqlite3` 中建立 `processed_documents` 資料表，其欄位需對應**第 3 節**的定義。
    *   實作一個 `save_analysis_result` 函式，此函式接收由 AI 分析回傳的結構化資料，以及**從 API 請求傳入的原始 `source_url`**，並將這兩部分資料一併存入資料庫。

5.  **建立 API 端點**
    *   在 `api_routes.py` 中，建立一個非同步的 API 端點 `POST /api/process_document`。
    *   此端點接收一個包含 `url` 的請求，並將該 `url` 交給 `processor.py` 進行背景處理。為確保 API 快速回應，它應立即回傳一個任務接收成功的訊息。

## 5. 測試設計 (Pytest)

*   **目錄**: 建立 `tests/test_document_processor_service/`。
*   **Mocking**: 大量使用 `pytest.mock` 來模擬 `universal_downloader`、`content_extractor` 和 `llm_service` 的行為，使我們能專注於測試 `document_processor_service` 本身的業務邏輯。
*   **單元測試 (`test_processor.py`)**:
    *   測試提示詞生成的正確性。
    *   測試從模擬的 `llm_service` 回傳的各種 JSON（格式正確、格式錯誤、包含空值等）是否能被正確處理。
*   **整合測試 (`test_api.py`)**:
    *   使用 `TestClient` 測試 `POST /api/process_document` 端點。
    *   驗證 API 是否能正確接收請求，並觸發（被 Mock 的）處理流程。

## 6. 參考檔案列表

本計畫將參考、整合或重構以下現有檔案的邏輯：

*   **核心工具**
    *   `src/tools/universal_downloader.py`: 用於下載文件。
    *   `src/tools/content_extractor.py`: 用於從文件中提取文字。
*   **核心服務**
    *   `services/llm_service/`: 作為本地 AI 分析的核心引擎。
*   **資料庫範本**
    *   `src/db/database.py`: 作為資料庫連線與操作的參考實作。

## 7. 測試範例

### 7.1. 觸發流程的輸入來源 (LINE 聊天記錄)
新服務將處理的是從類似以下聊天記錄的訊息中，提取出的文件 URL。

```
] 小作文天地的聊天記錄 儲存日期：2025/9/17 18:40

2025/4/3（週四）
14:36 069-0401669Crswin加入聊天
17:06 501-0723486Mason加入聊天
17:11 501-0723486Mason 四月小作文-0050元大台灣50 https://1drv.ms/u/s!AoaAyZHt1qThgRnnZPjmjLXlpMal?e=QtBZG4
17:13 502-0724579Cowboy加入聊天
17:13 502-0724579 Cowboy 四月小作文-來頡6799 https://drive.google.com/file/d/1RUl7XhxyJpxKO4RBX0AxeeyD4ABYPU_l/view?usp=sharing
17:54 500-0724304FOMO就剁手手加入聊天

2025/4/5（週六）
12:21 383-0488695 三寶 小作文-2424隴華
https://docs.google.com/document/d/10nDGa7nWuSZCLhU9qtR_VW8Cx-yQllk5/edit?usp=drive_link&ouid=105443695704290227678&rtpof=true&sd=true
14:09 503-0551726千千 四月小作文-日月光投控 3711 https://drive.google.com/file/d/1ADg9NnB10z3qjnSZPOn6BLh_Fz8wjY9T/view?usp=sharing
```

### 7.2. 文件內容範例 (用於分析測試)
以下文字是模擬從上述來源的 URL 中，下載並提取出的文件內容。這將作為「分析模組」的核心測試輸入。

**範例一 (源自 `...0050元大台灣50...`):**
> 我認為目前市場情緒過熱，雖然長期看好台灣整體經濟，但短期內有回檔風險。建議空手者可等待指數回測季線再分批布局，持股者可考慮部分獲利了結，保留現金水位。整體策略偏向保守觀望，但並非完全看空。

**範例二 (源自 `...2424隴華...`):**
> 該公司近期營收成長動能強勁，且在新產品線上布局完整，有望帶動下半年獲利。法人籌碼集中，技術線圖呈現多頭排列，是明確的看多訊號。建議積極型投資人可於現價買進，目標價上看 50 元，停損設於月線。

**範例三 (源自 `...日月光投控 3711...`):**
> 這是一份關於半導體封裝測試產業的綜合研究報告，詳細分析了全球供應鏈的變化、市場競爭格局，以及日月光在其中的技術優勢與挑戰。報告內容詳實，數據豐富，但未提供明確的買進或賣出建議，主要為產業趨勢分析。