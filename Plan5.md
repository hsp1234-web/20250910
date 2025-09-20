# 專案架構分析與債券分析功能實作方案 (V3 - 最終詳盡版)

## 一、 現有專案架構分析

### 1. 完整檔案樹狀結構圖

以下是專案的完整檔案結構，以利全面理解：
```
.
├── AGENTS.md
├── Log.md
├── Plan3.md, Plan4.md, Plan5.md
├── TOOLS_README.md
├── colabPro.py
├── config/
│   ├── circus.ini.template
│   └── config.json.template
├── pyproject.toml
├── pytest.ini
├── requirements/
│   ├── analysis.txt
│   ├── core.txt
│   ├── features_core.txt
│   ├── features_non_core.txt
│   ├── gemini.txt
│   ├── test.txt
│   └── transcriber.txt
├── scripts/
│   └── ... (多個腳本)
├── services/
│   └── key_service/
│       ├── main.py
│       └── requirements.txt
├── src/
│   ├── api/
│   │   ├── api_server.py
│   │   ├── dependencies.py
│   │   └── routes/
│   │       ├── ui.py
│   │       └── page1.py, ... (共 11 個頁面路由)
│   ├── core/
│   │   └── ... (共 7 個核心模組)
│   ├── db/
│   │   ├── database.sqlite3
│   │   ├── client.py
│   │   ├── database.py
│   │   ├── initialize_database.py
│   │   ├── log_handler.py
│   │   └── manager.py
│   ├── prompts/
│   │   └── default_prompts.json
│   ├── static/
│   │   ├── css/
│   │   └── ... (共 28 個 HTML 檔案)
│   └── tools/
│       └── ... (共 22 個工具模組)
├── tests/
│   └── conftest.py
└── 一級交易pro.py
```

### 2. 核心檔案與所有頁面功能註解

#### 核心後端檔案
- **`src/api/api_server.py`**: **主後端服務**。負責接收所有前端 HTTP 請求、管理 WebSocket，並將耗時任務非同步地交由背景處理。
- **`src/db/manager.py`**: **資料庫管理器服務**。獨立的 FastAPI 服務，是唯一能直接存取資料庫的元件。
- **`src/db/client.py`**: **資料庫客戶端**。讓主後端服務可以安全地請求「資料庫管理器服務」來操作資料庫。
- **`src/db/database.py`**: **資料庫 Schema 定義**。定義了專案的所有資料表結構和 SQL 操作函式。
- **`src/api/routes/ui.py`**: **UI 路由管理器**。定義了 URL 路徑與 HTML 頁面的對應關係。
- **`一級交易pro.py` / `colabPro.py`**: **核心分析腳本/啟動器**。包含了主要的金融分析流程，並可能是整個應用的啟動統籌腳本。

#### 所有前端頁面 (`src/static/*.html`)
- **`main.html`**: **專案入口主頁 (鳳凰主頁)**，提供各大功能模組的選擇。
- **`mp3.html`**: **(舊版) 音訊轉錄儀介面**。
- **`page1.html`**: **文件分析儀主介面**。
- **`page1_sub_ingestion.html`**, **`page1_sub_overview.html`**, **`page1_sub_export.html`**: 文件分析儀的子頁面，分別對應資料匯入、總覽和匯出。
- **`page2_downloader.html`**: **批次下載器介面**。
- **`page3_processor.html`**: **檔案處理與轉檔介面**。
- **`page4_stage1_ai.html`** 到 **`page4_stage4_download.html`**: **多階段 AI 分析流程**的各個步驟介面。
- **`page5_backup.html`**: **備份管理介面**。
- **`page6_keys.html`**: **API 金鑰管理介面**。
- **`page7_prompts.html`**: **AI 提示詞管理介面**。
- **`page8_file_details.html`**: **單一檔案的詳細資訊檢視器**。
- **`page9_dashboard.html`**: **績效儀表板介面**。
- **`page10_service_test.html`**: **微服務測試頁面**。
- **`history.html`**: **歷史紀錄頁面**。
- **`report_viewer.html`**: **報告檢視器頁面**。
- **`line_extractor.html`**: **LINE 貼文整理工具介面**。
- **`json_viewer.html`**, **`export_cards.html`**, **`export_table.html`**: 用於資料展示和匯出的輔助頁面。

### 3. 依賴管理檔案詳細用途
- **`pyproject.toml`**: 專案的標準設定檔，定義了專案名稱、版本等元數據。
- **`requirements/` 目錄**:
    - **`core.txt`**: **核心框架依賴**。提供 `api_server` 和 `db_manager` 運行的基礎，如 `fastapi`, `uvicorn`。
    - **`analysis.txt`**: **量化分析依賴**。為 `quantitative_analyzer.py` 提供股票分析所需套件。
    - **`gemini.txt`**: **AI 功能依賴**。為 `gemini_processor.py` 提供 Google Gemini AI 服務所需套件。
    - **`test.txt`**: **測試環境依賴**。執行自動化測試時才需要。
    - **`transcriber.txt`**: **音訊轉錄依賴**。為 `transcriber.py` 提供 Whisper 語音辨識所需套件。
    - **`features_core.txt` / `features_non_core.txt`**: **功能集依賴**。可能是為了區分部署時需要安裝的核心功能與非核心功能。
- **`services/key_service/requirements.txt`**: **獨立服務依賴**。`key_service` 擁有自己的依賴檔案，表明它可以作為一個獨立的微服務部署。

### 4. 服務間通訊方式
- **瀏覽器 <-> 主 API 服務**:
    - **HTTP**: 使用者透過瀏覽器發送 GET 請求獲取 HTML 頁面，透過 `fetch` API 發送 POST 請求來觸發後端任務。
    - **WebSocket**: 用於即時雙向通訊，伺服器可主動將任務的進度（如 `downloading`, `processing`, `completed`）推送給前端，實現動態更新。
- **主 API 服務 <-> 資料庫管理服務**:
    - **HTTP**: `api_server` 中的 `DBClient` 將所有資料庫操作（`add_task`, `get_status` 等）封裝成 JSON 格式的 HTTP POST 請求，發送給 `db_manager` 的 `/execute` 端點。這種方式確保了服務間的完全解耦。

---

## 二、 債券分析功能實作方案

基於以上極度詳細的分析，我們對三個方案的評估更具信心：

### 方案 A：最小改動整合方案
- **說明**：直接在現有架構上擴充，修改 `database.py` 新增資料表，修改 `api_server.py` 新增任務類型。
- **優點**：開發快速，符合現有模式。
- **缺點**：高耦合，未來債券分析的龐大數據量可能拖慢整個系統。

### 方案 B：獨立進程，共享資料庫服務方案
- **說明**：計算獨立，但仍透過 `DBClient` 將結果寫入同一個 `DB Manager` 服務。
- **優點**：計算過程不影響主服務的回應速度。
- **缺點**：資料庫服務仍是共享瓶頸。

### 方案 C：完全微服務化方案 (獨立資料庫 + 訊息佇列)
- **說明**：為債券分析建立全新的、獨立的服務、資料庫，並引入 Redis 作為通訊中介。
- **優點**：**最符合您「新增而不修改、獨立運作、高效能」的長遠目標**。完全解耦，擴充性最強。
- **缺點**：初期開發和部署需要引入並設定 Redis。

我將等待您的最終方案選擇，然後為您制定該方案的詳細開發計畫。
