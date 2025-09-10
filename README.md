# 鳳凰音訊轉錄儀 (Phoenix Transcriber)

[![zh-Hant](https://img.shields.io/badge/language-繁體中文-blue.svg)](README.md)

這是一個高效、可擴展的音訊轉錄專案，旨在提供一個可以透過 Web 介面輕鬆操作的語音轉文字服務。專案近期已整合 **YouTube 影片處理與 AI 分析** 功能。

---

## ⚡️ 如何啟動與測試

我們提供多種執行方式，請根據您的需求選擇。

### 方式一：本地開發與驗證 (建議)

這是最推薦的入門與驗證方式。單一指令即可完成所有環境設定並執行一次輕量級的快照測試，以確認系統是否正常運作。

**此方式適用於**：
*   首次設定開發環境。
*   快速驗證核心環境（Python, Node.js, 服務啟動）是否配置正確。

**如何使用**:
```bash
# 執行此指令將會自動安裝所有依賴、啟動伺服器、擷取快照，然後關閉。
bun run snapshot
```
當腳本顯示「🎉 輕量級快照腳本執行成功！」時，即表示您的開發環境已準備就緒。詳細的說明請參閱根目錄下的 `AGENTS.md`。

#### 測試策略 (Testing Strategy)

本專案的品質保證流程，優先採用**自動化斷言 (Automated Assertions)** 的方式來進行前端功能驗證，而非依賴視覺化截圖比對。我們強烈建議在 Playwright 測試腳本中，直接使用 `expect(locator)` 來驗證 UI 元素的狀態（如可見性、文字內容、屬性等）。

**理由如下**：
*   **可靠性**: 自動化斷言比人眼或 AI 視覺審查更精確、更可重複。
*   **效率**: 測試執行速度更快，能提供即時回饋。
*   **輕量化**: 避免了為了進行視覺化處理而需要安裝大量系統級圖形介面依賴（如 `Xvfb`、`GTK` 等），讓開發與 CI/CD 環境更乾淨、更穩定。

---

### 方式二：手動啟動後端服務 (進階)

如果您需要一個**持續運行的後端服務**來進行前端開發或手動測試，請使用 `circus` 直接啟動。

**此方式適用於**：
*   本地端開啟 `src/static/mp3.html` 進行手動功能測試。
*   需要手動連接後端進行除錯的場景。

**注意**：此方式不會自動安裝依賴，請先執行一次 `bun run snapshot` 以確保環境完整。

**如何使用**:
```bash
# 啟動所有後端服務
python -m circus.circusd circus.ini

# 完成測試後，可使用以下指令關閉服務
python -m circus.circusctl quit
```
服務啟動後，您可以透過 `http://127.0.0.1:42649` 訪問前端介面。

---

### 方式三：僅驗證後端整合 (`scripts/local_run.py`)

`scripts/local_run.py` 是一個**自動化的後端整合測試腳本**。它會啟動所有服務，提交一個測試任務，並在任務完成後自動關閉。它**不會**啟動或測試前端 UI。

**此方式適用於**：
*   快速驗證後端修改是否引發問題。
*   在 CI/CD 環境中進行後端自動化檢查。

**如何使用**:
```bash
python scripts/local_run.py
```

---

### 方式四：在 Google Colab 中部署 (`scripts/colab.py`)

`scripts/colab.py` 是專為在 Google Colab 環境中一鍵部署和運行本專案而設計的啟動器。

**如何使用**:
1.  在 Google Colab 中開啟一個新的筆記本。
2.  將 `colab.py` 的完整程式碼複製並貼到 Colab 的儲存格中。
3.  執行該儲存格。儀表板將會顯示，並在伺服器就緒後提供一個代理連結供您訪問。

---

## 📈 專案狀態

**核心功能與測試 - ✅ 已完成**

*   [x] **架構重構**：已完成穩定的多程序架構（協調器、資料庫管理器、API 伺服器）。
*   [x] **功能完整**：本地檔案轉錄與 YouTube 影片處理功能均已完整實現。
*   [x] **測試穩定**：`local_run.py` 後端整合測試與 `bun run snapshot` 環境驗證腳本運作正常。

---
## 📁 檔案結構 (新版)

```
hsp1234-web/
├── .github/              # CI/CD 工作流程
├── .vscode/              # VS Code 編輯器設定
├── build/                # 建置後的產出物
├── config/               # 所有環境設定檔 (circus.ini)
├── docs/                 # 專案文件
├── logs/                 # 執行時產生的日誌檔案
├── scripts/              # 各類輔助腳本 (部署、測試啟動器)
├── src/                  # 主要應用程式原始碼
│   ├── api/              # API 伺服器 (api_server.py)
│   ├── core/             # 核心商業邏輯 (orchestrator.py)
│   ├── db/               # 資料庫相關模組
│   ├── static/           # 靜態檔案 (HTML, CSS, 前端 JS)
│   ├── tasks/            # 背景任務/Worker (worker.py)
│   ├── tests/            # 所有測試檔案 (單元測試、E2E 測試)
│   └── tools/            # 專案使用的工具模組
├── .gitignore            # Git 忽略清單
├── AGENTS.md             # (重要) 給 AI 開發者的說明文件
├── package.json          # Node.js 專案依賴
├── playwright.config.js  # Playwright E2E 測試設定
├── pyproject.toml        # Python 專案設定
├── requirements.txt      # Python 專案依賴
└── README.md             # 專案主說明文件
```
