# 輕量級啟動與整合測試流程

本文件旨在提供一個標準化、輕量級的流程，用於在本地開發環境中啟動並測試本應用程式。此流程旨在避開不必要的、大型的依賴套件（如語音轉文字模型），以實現快速啟動和驗證。

## 1. 環境準備：精準安裝依賴

為避免下載不必要的套件導致環境過大或啟動超時，我們只安裝執行核心功能（Web 伺服器、資料庫、AI 分析）所必需的套件。

**指令：**
請在專案根目錄下，依序執行以下指令。建議使用 `uv` 以獲得最快的安裝速度。

```bash
# 首先安裝核心 Web 框架與工具
uv pip install -r requirements/core.txt --system

# 接著安裝 Gemini AI 分析所需的套件
uv pip install -r requirements/gemini.txt --system
```

**請勿**直接安裝 `requirements.txt` 或 `requirements/transcriber.txt`，除非您確實需要執行語音轉文字相關功能。

## 2. 啟動應用程式：執行主協調器

本應用程式的正確入口點是 `src/core/orchestrator.py`。此協調器會負責依序、正確地啟動所有必要的背景服務（如 `db_manager` 和 `api_server`）。

**指令：**
建議以模組（`-m`）的形式執行，以確保 Python 路徑的正確性。同時，將日誌輸出重導向到檔案中以便後續分析。

```bash
# 在專案根目錄下執行
python -m src.core.orchestrator > orchestrator.log 2>&1 &
```

## 3. 驗證啟動狀態

在執行啟動指令後，請稍待幾秒鐘，然後檢查日誌檔案以確認服務是否成功啟動。

**指令：**
```bash
# 讀取日誌檔案內容
read_file("orchestrator.log")
```

**成功的日誌應包含以下關鍵訊息：**
- `資料庫管理者已就緒，監聽於埠號: ...`
- `API 伺服器程序已啟動，PID: ...`
- `[api_server] Uvicorn running on http://...`
- `[協調器進入監控模式]`

看到以上訊息，即代表整個應用程式後端已準備就緒。

## 4. 手動 API 整合測試（範例）

在服務成功啟動後，可以使用 `curl` 等工具來模擬前端操作，以測試後端 API 的正確性。

**範例：獲取分析任務狀態**
```bash
# 假設 API 伺服器運行在 8001 埠
curl http://127.0.0.1:8001/api/analyzer/analysis_status
```

**範例：啟動第一階段分析**
```bash
curl -X POST http://127.0.0.1:8001/api/analyzer/start_stage1_analysis \
-H "Content-Type: application/json" \
-d '{"file_ids": [1], "model_name": "gemini-1.5-flash-latest"}'
```

根據以上流程，即可在不污染環境、不耗費過多時間的前提下，對核心功能進行有效的開發與測試。
