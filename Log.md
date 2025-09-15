## 980號 - E2E 測試框架建置與架構修復 (2025-09-15T10:22:29.776255+08:00)

### 動機
本次任務的核心目標是為後端系統建立一個穩健的端對端（E2E）整合測試框架。在嘗試為「頁面一」和「頁面二」編寫測試的過程中，發現了一個嚴重的架構性缺陷，導致背景任務無法被可靠地測試。因此，任務的動機擴展為：不僅要建立測試，還要修復所有阻礙測試的底層問題。

### 核心變更
1.  **架構修復 (依賴注入)**:
    -   **問題**: 發現 `page2_downloader.py` 和 `page3_processor.py` 中的背景任務執行緒，無法繼承主程序設定的環境變數（特別是 `DB_MANAGER_PORT`），導致它們總是嘗試連線到一個錯誤的、寫死的預設資料庫服務埠號。
    -   **解決方案**: 修改了這兩個模組，採用依賴注入模式。將主 API 執行緒中已正確配置的 `DBClient` 物件，作為參數直接傳遞給背景任務函式。這從根本上確保了資料庫連線的一致性。

2.  **完善依賴管理**:
    -   在測試過程中，發現了多個被遺漏的核心應用依賴。已將 `psutil`, `python-multipart`, `uvicorn` 新增至 `requirements/core.txt`。
    -   將測試框架所需的 `pytest-xdist` 新增至 `requirements/test.txt`。
    -   確認了 `google-generativeai` 依賴存在於 `requirements/gemini.txt` 中，並在測試前確保其被安裝。

### 測試
1.  **E2E 測試環境 (`tests/conftest.py`)**:
    -   建立了一個名為 `live_services` 的 `session-scoped` 的 `pytest` fixture。
    -   此 fixture 能在測試開始前，完整地啟動後端的所有服務（`db_manager`, `api_server`），並在結束後自動關閉，為整合測試提供了真實且隔離的運行環境。

2.  **新增測試案例**:
    -   **`test_page1_ingestion_e2e.py`**: 驗證了「頁面一」的完整流程，從 API 呼叫到資料庫寫入均符合預期。
    -   **`test_page2_downloader_e2e.py`**: 在修復了架構問題後，此測試驗證了「頁面二」的背景下載任務能正確更新資料庫狀態，並在檔案系統中建立對應的檔案。

3.  **修復既有測試**:
    -   修復了 `test_integration.py` 和 `test_stage1_analysis.py` 中因本次架構變更和依賴問題而導致的失敗。
    -   透過在 E2E 測試案例執行前清理資料表，解決了因 `session-scoped` fixture 造成的資料庫狀態污染問題。

### 成果
經過一系列的重構、除錯與測試，我們現在擁有一個功能正常的測試套件，其中包含 26 個通過的測試案例。更重要的是，系統的穩定性和可測試性得到了顯著提升，為後續功能的開發和迭代奠定了堅實的品質基礎。

---

# Hermes 計畫 - 前後端架構對照說明文件

## 一、系統核心設計理念
本系統採用管線式 (Pipeline) 架構，將複雜的資料處理流程，拆解為八個獨立且功能明確的前端頁面對應模組。使用者透過前端介面逐步引導資料完成從「擷取」到「分析」的完整生命週期。後端則提供一系列 RESTful API 端點與前端對接，並透過中心化的 SQLite 資料庫來管理所有任務的狀態。

## 二、前端頁面與後端 API 詳解
以下將逐一說明每個前端頁面的核心功能，及其對應的後端 API 端點和處理邏輯。

### 頁面一：資料擷取 (Ingestion)
*   **前端功能**：提供一個文字輸入框，讓使用者貼上 LINE 的聊天紀錄。
*   **使用者操作**：使用者貼上文字後，點擊「開始擷取」按鈕。
*   **觸發 API 端點**：`POST /api/ingestion/extract_urls`
*   **後端處理流程**：
    1.  後端 API 接收到請求，取得請求主體 (Body) 中的 `{"text": "..."}` 內容。
    2.  呼叫 `tools.url_extractor` 模組，使用正規表示式 (Regex) 逐行解析文字。
    3.  精準識別出每一則訊息的 **發布日期**、**作者** 以及 **Google Drive/Docs 網址**。
    4.  將這些結構化資料寫入資料庫。
*   **資料庫互動**：在 `extracted_urls` 資料表中，為每一個成功解析出的網址 `INSERT` 一筆新的紀錄。並將該筆紀錄的 `status` 欄位初始值設為 `pending`。

### 頁面二：批次下載 (Downloader)
*   **前端功能**：以列表形式，展示所有 `status` 為 `pending` 的網址紀錄。
*   **使用者操作**：使用者勾選希望下載的項目，點擊「開始批次下載」按鈕。
*   **觸發 API 端點**：`POST /api/downloader/start_downloads`
*   **後端處理流程**：
    1.  API 接收到一個包含 `extracted_urls` 表 ID 的陣列，例如 `{"ids": [1, 5, 12]}`。
    2.  後端立即將這些 ID 對應紀錄的 `status` 更新為 `downloading`，讓前端可以即時顯示「下載中」的狀態。
    3.  系統在背景為每一個 ID 啟動一個獨立的下載任務，呼叫 `tools.drive_downloader` 工具，使用 `gdown` 函式庫從 Google Drive 下載檔案。
*   **資料庫互動**：
    -   任務開始時：`status` 更新為 `downloading`。
    -   下載成功時：`status` 更新為 `completed`，並將檔案的本地儲存路徑寫入 `local_path` 欄位。
    -   下載失敗時：`status` 更新為 `download_failed`，並記錄錯誤訊息。

### 頁面三：檔案處理 (Processor)
*   **前端功能**：展示所有已成功下載 (`status = completed`) 的檔案列表。
*   **使用者操作**：使用者勾選希望處理的檔案，點擊「開始處理內容」按鈕。
*   **觸發 API 端點**：`POST /api/processor/start_processing`
*   **後端處理流程**：
    1.  API 接收到檔案的 ID 列表 `{"ids": [...]}`。
    2.  立即將 `extracted_urls` 中對應紀錄的 `status` 更新為 `processing`。
    3.  在背景為每個檔案執行 `tools.content_extractor`，此工具支援 PDF, DOCX 等多種格式，會提取其中的純文字與圖片內容，並計算檔案的 `SHA256` 雜湊值。
    4.  **關鍵步驟**：內容提取成功後，系統會將提取出的文字內容，在 `analysis_tasks` 資料表中建立一筆新的任務紀錄，為下一步的 AI 分析做準備。
*   **資料庫互動**：
    -   `extracted_urls` 表：`status` 更新為 `processed`。填入 `file_hash`, `extracted_text` 等欄位。
    -   `analysis_tasks` 表：`INSERT` 一筆新的紀錄，並透過 `url_source_id` 欄位與 `extracted_urls` 的紀錄建立關聯。

### 頁面四：AI 分析 (Analyzer)
*   **前端功能**：提供一個介面，分兩階段啟動對已處理檔案的 AI 分析。
*   **使用者操作**：使用者選擇檔案，點擊「啟動第一階段分析」。待第一階段完成後，再點擊「啟動第二階段分析以生成報告」。
*   **觸發 API 端點**：
    -   `POST /api/analyzer/start_stage1_analysis`
    -   `POST /api/analyzer/start_stage2_analysis`
*   **後端處理流程**：
    1.  **第一階段**：接收 `file_ids`，讀取 `analysis_tasks` 表中的文字內容，呼叫 `GeminiManager` 將非結構化文字轉換為結構化的 JSON 資料。
    2.  **第二階段**：接收 `task_ids`，讀取第一階段產生的 JSON，再次呼叫 `GeminiManager` 生成一份完整的 HTML 分析報告。
*   **資料庫互動**：主要在 `analysis_tasks` 表中更新進度：`stage1_status` 更新為 `completed`，並填入 `stage1_json_path`。`stage2_status` 更新為 `completed`，並填入 `stage2_report_path`。

### 頁面五：系統備份 (Backup)
*   **前端功能**：提供一個簡單的按鈕，用於打包備份系統核心資料。
*   **使用者操作**：點擊「建立備份」按鈕。
*   **觸發 API 端點**：`POST /api/backup/start_backup`
*   **後端處理流程**：在背景執行 `tools.gdrive_backup` 模組，將 `src/db/tasks.db` 資料庫檔案和整個 `downloads/` 目錄壓縮成一個 `.zip` 檔案。
*   **資料庫互動**：無直接互動（僅讀取資料庫檔案本身）。

### 頁面六：金鑰管理 (Key Manager)
*   **前端功能**：提供一個 CRUD (增刪查改) 介面，用於管理 Gemini API 金鑰。
*   **使用者操作**：使用者在此頁面新增、刪除或查看 API 金鑰。
*   **觸發 API 端點**：`GET`, `POST`, `DELETE /api/keys`
*   **後端處理流程**：所有操作均透過 `core.key_manager` 模組，直接讀寫一個獨立的 `src/db/secrets/keys.json` 檔案。此設計將敏感金鑰與主業務資料庫完全隔離。
*   **資料庫互動**：無。

### 頁面七：提示詞管理 (Prompt Manager)
*   **前端功能**：提供兩個文字區塊，讓使用者可以自訂並儲存 AI 分析的兩個階段所使用的提示詞 (Prompt)。
*   **使用者操作**：修改提示詞內容後，點擊「儲存」按鈕。
*   **觸發 API 端點**：`GET`, `POST /api/prompts`
*   **後端處理流程**：透過 `core.prompt_manager` 模組，直接讀寫 `src/prompts/default_prompts.json` 檔案。
*   **資料庫互動**：無。

### 頁面八：檔案總覽 (Details)
*   **前端功能**：提供一個詳細視圖，展示單一檔案從被擷取到分析完成的完整生命週期。
*   **使用者操作**：在某個列表中點擊一個檔案的「詳情」按鈕。
*   **觸發 API 端點**：`GET /api/details/{file_hash}`
*   **後端處理流程**：
    1.  API 接收到檔案的 `SHA256` 雜湊值。
    2.  使用此雜湊值，去 `extracted_urls` 表中查詢所有相關的紀錄（處理重複上傳的檔案）。
    3.  再用查到的 id，去 `analysis_tasks` 表中找到對應的 AI 分析紀錄。
    4.  將所有查詢到的資訊彙整成一個 JSON 物件後回傳給前端。
*   **資料庫互動**：唯讀 (Read-Only) 操作，會同時查詢 `extracted_urls` 和 `analysis_tasks` 兩個資料表。
