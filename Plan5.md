# 專案架構分析與債券分析功能實作方案 (V4 - 微服務架構)

**最後更新: 2025/9/21 04:16**

## 一、 現有專案架構分析

### 1. 完整檔案樹狀結構圖 (截至 2025-09-21)
```
.
├── AGENTS.md
├── Log.md
├── Plan3.md
├── Plan4.md
├── Plan5.md
├── TOOLS_README.md
├── cleanup_report_20250917.md
├── colabPro.py
├── config
│   ├── circus.ini.template
│   └── config.json.template
├── pyproject.toml
├── pytest.ini
├── requirements
│   ├── analysis.txt
│   ├── core.txt
│   ├── features_core.txt
│   ├── features_non_core.txt
│   ├── gemini.txt
│   ├── test.txt
│   └── transcriber.txt
├── scripts
│   ├── check_deps.py
│   ├── colab_key_injector.py
│   ├── migrate_keys_to_db.py
│   ├── quantitative_analysis_poc.py
│   ├── run_processing_pipeline.py
│   └── time.py
├── services
│   ├── bond_data_service
│   └── key_service
├── src
│   ├── api
│   ├── core
│   ├── db
│   ├── prompts
│   ├── static
│   └── tools
├── tests
│   ├── __pycache__
│   ├── conftest.py
│   └── test_bond_service_startup.py
└── 一級交易pro.py
```

### 2. 核心檔案與所有頁面功能註解
(此部分內容與 V3 版相同，維持不變)

#### 核心後端檔案
- **`src/api/api_server.py`**: **主後端服務**。負責接收所有前端 HTTP 請求、管理 WebSocket，並將耗時任務非同步地交由背景處理。
- **`src/db/manager.py`**: **資料庫管理器服務**。獨立的 FastAPI 服務，是唯一能直接存取資料庫的元件。
- **`src/db/client.py`**: **資料庫客戶端**。讓主後端服務可以安全地請求「資料庫管理器服務」來操作資料庫。
- **`src/db/database.py`**: **資料庫 Schema 定義**。定義了專案的所有資料表結構和 SQL 操作函式。
- **`src/api/routes/ui.py`**: **UI 路由管理器**。定義了 URL 路徑與 HTML 頁面的對應關係。
- **`一級交易pro.py` / `colabPro.py`**: **核心分析腳本/啟動器**。包含了主要的金融分析流程，並可能是整個應用的啟動統籌腳本。

#### 所有前端頁面 (`src/static/*.html`)
- **`main.html`**: **專案入口主頁 (鳳凰主頁)**，提供各大功能模組的選擇。
- **`page_bond.html`**: **(新) 債券分析儀表板**。
... (其餘頁面省略) ...

### 3. 依賴管理檔案詳細用途
(此部分內容與 V3 版相同，維持不變)

### 4. 服務間通訊方式
(此部分內容與 V3 版相同，維持不變)

---

## 二、 債券分析功能實作方案 (已採納)

基於先前的討論與演進，專案已正式採納 **方案 C：完全微服務化方案**，以確保長期的可擴充性與穩定性。

### 1. 新增微服務：`bond_data_service`
- **位置**: `services/bond_data_service/`
- **目的**: 專門負責所有與債券分析相關的宏觀經濟數據的獲取、儲存與供給。
- **架構**:
    - **框架**: 使用 FastAPI 建立一個獨立、輕量級的 API 服務。
    - **環境**: 使用 `uv` 和 `venv` 建立獨立的虛擬環境 (`.venv`)，其依賴由專屬的 `requirements.txt` 管理，與主應用完全隔離。
    - **資料庫**: 擁有自己獨立的 SQLite 資料庫 (`bond_data.sqlite3`)，用於儲存時間序列數據。
    - **啟動**: 由主應用的 `orchestrator.py` 在啟動時，以 `uvicorn` 指令自動化地啟動此微服務。
- **核心模組**:
    - `main.py`: FastAPI 應用主體，負責定義 API 端點 (如 `/ping`, `/fetch/{indicator}`, `/data/{indicator}`)。
    - `database.py`: 負責資料庫的連線與初始化 (`macro_data` 資料表)。
    - `data_manager.py`: 核心業務邏輯層，負責調度下方的資料抓取器，並處理資料的儲存與讀取。
    - `data_fetchers/`: 一個模組化的目錄，每個檔案負責抓取一個特定的經濟指標 (例如 `fred_gdp_fetcher.py`)。

### 2. 前後端通訊 (服務發現)
- **問題**: `bond_data_service` 由 `orchestrator` 啟動在一個動態分配的埠號上，前端無法直接知道其位址。
- **解決方案**:
    1.  `orchestrator.py` 在啟動所有微服務後，會將其服務名稱與對應的埠號寫入一個共享的註冊檔案 (`/tmp/service_registry.json`)。
    2.  主應用 (`api_server.py`) 提供一個 `/api/service_registry` 端點，讓前端可以查詢此註冊檔案。
    3.  前端 (`page_bond.js`) 在載入時，會先向主應用請求服務註冊資訊，動態地獲取 `bond_data_service` 的正確位址，然後再向其發送後續的資料請求。

---

## 三、 當前開發狀態 (截至 2025-09-21)

- **後端**:
    - ✅ `bond_data_service` 微服務的基礎架構已建立完成。
    - ✅ 已為 GDP, CPI, Fed Funds Rate 建立獨立的資料抓取模組 (POC 驗證通過)。
    - ✅ 微服務的資料庫、DataManager、API 端點 (fetch/data) 均已實作。
    - ✅ `orchestrator.py` 的啟動錯誤已被修正，現在能正確啟動微服務。
    - ✅ 已建立 `pytest` 元件測試，可驗證微服務的啟動與健康狀態。
    - ⚠️ ISM 製造業 PMI 指標因 FRED API 停止供應，暫時擱置，待尋找新的資料來源。
- **前端**:
    - ✅ `page_bond.html` 的前端頁面骨架與 CSS 樣式已建立完成。
    - ✅ 已引入 Chart.js 圖表庫。
    - ✅ 已實作與後端微服務的動態服務發現機制。
    - ✅ 已完成頁面載入時的圖表自動繪製，以及手動觸發資料更新的完整互動邏輯。
- **下一步**:
    - 尋找並實作 ISM 指標的替代資料來源。
    - 對前端 UI/UX 進行進一步的細節打磨。
    - 擴充更多「層級二」、「層級三」的資料指標抓取器與對應圖表。
