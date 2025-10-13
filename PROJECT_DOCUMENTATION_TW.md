# 專案架構與執行流程說明文件 (繁體中文)

本文檔旨在提供對本專案的全面性理解，涵蓋其核心架構、執行流程，並提供一份詳盡的檔案功能清單。

## 1. 專案概觀與核心架構

本專案採用一個現代化的**微服務架構 (Microservices Architecture)**，旨在將不同的功能模組解耦，以提高可維護性、擴展性和部署的靈活性。整個系統由三個主要部分協同工作：

1.  **前端使用者介面 (Frontend UI)**：一系列靜態的 HTML, CSS, 和 JavaScript 檔案，提供使用者操作的圖形介面。
2.  **後端 API 閘道器 (Backend API Gateway)**：一個基於 FastAPI 的核心伺服器，作為前端與所有後端服務溝通的統一入口。
3.  **後端微服務 (Backend Microservices)**：一系列獨立的、專注於特定任務的服務，例如語言模型處理、資料庫管理、資料抓取等。

### 執行流程

專案的典型執行流程如下：

1.  **啟動 (Colab 環境)**：使用者在 Google Colaboratory 環境中執行 `colabPro.py` 腳本。
2.  **環境準備 (`colabPro.py`)**：
    *   此腳本首先會從 GitHub 下載最新版本的專案原始碼。
    *   接著，它會安裝所有必要的 Python 依賴套件。
    *   最重要的是，它會啟動後端的**協調器 (`orchestrator.py`)**。
3.  **服務協調 (`orchestrator.py`)**：
    *   協調器是整個後端系統的「指揮中心」。
    *   它會自動掃描 `services/` 目錄，為每一個微服務建立獨立的運行環境，並啟動它們。
    *   同時，它也會啟動核心的 **API 閘道器 (`api_server.py`)**。
    *   所有已啟動服務的位址（主機和埠號）都會被記錄在一個共享的「服務註冊表」檔案中，以供其他服務查詢。
4.  **使用者互動**：
    *   `colabPro.py` 會產生一個公開的網路連結 (URL)。使用者透過瀏覽器訪問此連結，載入由 `api_server.py` 提供的前端介面。
    *   當使用者在前端頁面上進行操作（例如點擊按鈕），瀏覽器的 JavaScript 會向 `api_server.py` 的某個 API 端點發送請求。
5.  **請求處理 (`api_server.py`)**：
    *   API 閘道器接收到請求。
    *   如果請求是針對某個微服務的功能，閘道器會查詢「服務註冊表」，找到對應微服務的位址，然後將請求轉發過去。
    *   微服務處理完請求後，將結果返回給閘道器，閘道器再將最終結果傳回給前端。
    *   對於下載、AI分析等耗時長的任務，API 伺服器會採用非同步處理模式，並透過 WebSocket 將即時進度更新推送給前端。

這種架構將「介面」和「功能」完全分離，使得開發和維護變得更加高效和清晰。

---

## 2. `colabPro.py` 深度解析

`colabPro.py` 是專為在 Google Colaboratory 環境中一鍵部署和啟動整個專案而設計的**啟動器 (Launcher)**。它將複雜的後端設定流程完全自動化，讓使用者無需關心底層細節。

其核心功能包括：

*   **版本控制**：自動從指定的 GitHub 分支下載最新的程式碼，確保環境的一致性。
*   **依賴管理**：智慧地檢查並安裝所有後端服務所需的 Python 套件。
*   **安全金鑰注入**：能夠安全地從 Colab 的 Secrets Manager 中讀取 API 金鑰（例如 Google API Key, FRED API Key），並將它們注入到後端服務的運行環境中，避免了金鑰硬編碼的風險。
*   **服務啟動**：作為父進程，負責啟動 `src/core/orchestrator.py`，從而拉起整個後端微服務叢集。
*   **遠端存取通道**：自動設定如 `cloudflared` 或 `localtunnel` 等工具，產生一個公開的 URL，讓使用者可以從任何地方存取運行在 Colab 虛擬機上的服務。
*   **動態儀表板**：在 Colab 的輸出儲存格中提供一個即時更新的文字介面，動態顯示系統的運行日誌、資源使用率（CPU/RAM）、啟動狀態以及所有可用的公開存取網址。

總而言之，`colabPro.py` 是使用者與這個複雜系統之間最重要的橋樑，它極大地簡化了部署和操作的複雜度。

---

## 3. 完整檔案清單與功能說明

以下是專案中所有檔案和目錄的詳細功能說明。

### 根目錄 (`./`)

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `config/` | 存放專案的設定檔模板。 |
| `data/` | 存放由應用程式下載或產生的資料。 |
| `docs/` | 包含專案的各類說明文件、研究報告和計畫。 |
| `requirements/` | 存放不同模組的 Python 依賴套件清單。 |
| `scripts/` | 包含各種輔助腳本，用於資料庫遷移、金鑰注入等一次性任務。 |
| `services/` | **核心目錄**：包含所有獨立的後端微服務。 |
| `src/` | **核心目錄**：包含專案的主要原始碼，如 API 伺服器、核心邏輯和靜態前端檔案。 |
| `tests/` | 包含專案的單元測試和整合測試。 |
| `.gitignore` | 指定 Git 版本控制應忽略的檔案和目錄 (例如，日誌、資料庫檔案、虛擬環境)。 |
| `README.md` | 提供專案架構和命名規則的簡要說明。 |
| `colabPro.py` | **[關鍵檔案]** Google Colab 環境專用的一鍵啟動器，詳見第二節。 |
| `requirements.txt` | 根目錄級別的依賴清單，通常用於本地開發環境設定。 |
| `setup_environment.sh` | 一個 Shell 腳本，可能用於設定本地開發環境。 |
| `...` | 其他檔案多為開發過程中的臨時文件、報告或測試腳本。 |

### `config/`

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `circus.ini.template` | `circus` (一個進程管理器) 的設定檔模板。 |
| `config.json.template` | 專案通用設定檔的模板。 |

### `data/`

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `downloads/` | 存放從網路上下載的原始檔案。 |

### `docs/`

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `LLM_POC_2025/` | 存放 2025 年大型語言模型 (LLM) 概念驗證 (POC) 的相關報告和測試資料。 |
| `Project_Plans/` | 存放專案開發過程中的不同階段計畫文件。 |
| `Research_Reports/` | 存放各類研究報告。 |
| `System_Documentation/` | 存放更詳細的系統級說明文件，例如給 AI Agent 的指示。 |

### `requirements/`

此目錄將不同功能的依賴分開管理，使得環境可以按需安裝。

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `core.txt` | 核心服務 (如 API 伺服器) 運行的基本依賴。 |
| `downloader.txt` | 專門用於下載功能 (如 `yt-dlp`) 的依賴。 |
| `gemini.txt` | 與 Google Gemini 模型互動所需的依賴。 |
| `test.txt` | 運行測試所需的依賴。 |
| `...` | 其他檔案對應不同子功能的依賴。 |

### `scripts/`

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `check_deps.py` | 檢查 Python 環境中是否已安裝所需套件的腳本。 |
| `colab_key_injector.py` | **[關鍵腳本]** 由 `colabPro.py` 呼叫，負責將 API 金鑰寫入資料庫。 |
| `migrate_keys_to_db.py` | 用於將舊格式的金鑰遷移到新資料庫結構的腳本。 |
| `...` | 其他為特定 POC 或資料處理任務的腳本。 |

### `services/` - 微服務核心

這是所有後端微服務的家。每個子目錄都是一個獨立的、可運行的 FastAPI 應用。

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `bond_data_service/` | 提供債券市場相關數據的微服務。 |
| `document_processor_service/` | 處理文件（如 OCR、文字提取）的微服務。 |
| `key_master_service/` | (似乎是舊版) 金鑰管理服務。 |
| `line_parser_service/` | 解析 LINE 聊天記錄的專用微服務。 |
| `llm_service/` | **[關鍵服務]** 連接並管理大型語言模型 (如 Ollama) 的微服務，提供 AI 分析能力。 |
| `stock_id_extractor_service/` | 從文本中提取股票代號的微服務。 |
| `__init__.py` | 將 `services` 目錄標示為一個 Python 套件。 |

#### `services/bond_data_service/`

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `data_fetchers/` | 包含從不同來源 (FRED, Yahoo Finance) 抓取特定數據的模組。 |
| `main.py` | 該微服務的 FastAPI 應用主檔案。 |
| `repository.py` | 處理數據庫操作和業務邏輯。 |
| `service.py` | 包含服務的核心業務邏輯。 |

#### `services/line_parser_service/`

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `logic.py` | 包含解析 LINE 聊天記錄的核心邏輯。 |
| `main.py` | 該微服務的 FastAPI 應用主檔案。 |
| `universal_downloader.py` | 通用的下載工具模組。 |

#### `services/llm_service/`

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `main.py` | 該微服務的 FastAPI 應用主檔案。 |
| `model_manager.py` | 管理 Ollama 模型的下載和載入。 |

### `src/` - 應用程式主要原始碼

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `api/` | **[核心目錄]** 包含 API 伺服器的所有程式碼。 |
| `core/` | **[核心目錄]** 包含專案的核心共用模組，如協調器、金鑰管理器等。 |
| `db/` | **[核心目錄]** 包含所有與資料庫互動的模組。 |
| `prompts/` | 存放預設的 AI 提示詞 (prompts)。 |
| `static/` | **[核心目錄]** 存放所有前端檔案 (HTML, CSS, JavaScript)。 |
| `tools/` | 存放被後端服務呼叫的各種工具腳本 (如下載器、分析器)。 |

#### `src/api/`

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `routes/` | 將不同的 API 端點按功能切分成獨立的模組。 |
| `api_server.py` | **[關鍵檔案]** API 閘道器主程式，整合所有路由，處理 HTTP 請求和 WebSocket。 |
| `dependencies.py` | 存放 FastAPI 的依賴注入項，如資料庫客戶端實例。 |

#### `src/core/`

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `orchestrator.py` | **[關鍵檔案]** 微服務協調器，負責啟動和管理所有後端服務。 |
| `key_manager.py` | 處理 API 金鑰的增、刪、查、改和驗證邏輯。 |
| `service_discovery.py` | 提供查詢服務註冊表以找到微服務位址的功能。 |
| `workflow_engine.py` | 指令式工作流引擎的核心實現。 |
| `...` | 其他為各種共用的核心工具模組。 |

#### `src/db/`

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `client.py` | 提供一個簡單的客戶端，讓其他服務可以與資料庫管理器通訊。 |
| `database.py` | 定義資料庫的 schema (結構) 和核心操作函式。 |
| `manager.py` | 一個獨立的 FastAPI 應用，作為資料庫的統一存取點，確保資料操作的原子性和一致性。 |
| `database.sqlite3` | SQLite 資料庫檔案的模板或預設實例。 |

#### `src/static/`

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `css/` | 存放所有 CSS 樣式表。 |
| `js/` | 存放所有前端 JavaScript 檔案。 |
| `main.html` | 專案的單頁應用程式主入口頁面。 |
| `page_bond.html` | 債券數據分析頁面。 |
| `primary_dealer_analysis.html` | 主要交易商分析頁面。 |
| `...` | 其他 HTML 檔案對應專案的各個功能分頁。 |

#### `src/tools/`

此目錄存放被服務呼叫的、執行具體任務的腳本。

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `gemini_processor.py` | 封裝了與 Google Gemini API 互動的所有邏輯。 |
| `youtube_downloader.py` | 使用 `yt-dlp` 下載 YouTube 影片或音訊。 |
| `transcriber.py` | 使用 `whisper` 模型進行語音轉文字。 |
| `url_extractor.py` | 從文本中提取 URL。 |
| `...` | 其他為各種資料處理和分析的工具。 |

### `tests/`

此目錄結構與 `src/` 和 `services/` 相對應，用於存放相關模組的測試程式碼。

| 檔案/目錄 | 功能說明 |
| :--- | :--- |
| `api/` | 存放 API 伺服器相關的測試。 |
| `test_document_processor_service/` | `document_processor_service` 的單元測試。 |
| `...` | 其他目錄和檔案對應不同模組的測試。 |
