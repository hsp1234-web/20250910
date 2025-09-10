# 後續開發與驗證計畫 (plan2.md)

## 導言
本文件旨在引導下一位 AI 助手順利接手此專案。目前的專案已經修復了先前版本中一個關鍵的 404 錯誤，並補全了幾個缺失的核心依賴。首要任務是先驗證這些修復的有效性，然後再繼續後續的功能開發。

---

## Part 1: 驗證現有修復
**目標：** 確認「批次下載」功能的 404 錯誤已修復，且應用程式可以穩定運行。

請依序執行以下步驟來進行端到端 (End-to-End) 測試：

**1. 啟動伺服器**
由於專案的特殊啟動需求，請務必使用以下指令在背景啟動伺服器。此指令會設定正確的 `PYTHONPATH` 並將日誌輸出到 `server.log`：
```bash
PYTHONPATH=src python src/core/orchestrator.py > server.log 2>&1 &
```

**2. 等待並取得 URL**
伺服器需要一些時間來初始化。請等待約 15 秒，然後從日誌檔案中提取出應用程式正在運行的 URL。
```bash
# 等待 15 秒
sleep 15
# 從日誌中提取 PROXY_URL
URL=$(grep "PROXY_URL" server.log | tail -n 1 | sed 's/PROXY_URL: //')
echo "伺服器應在以下 URL 運行: $URL"
```

**3. 執行 Playwright 自動化測試**
上一位助手已經編寫了一個自動化測試腳本。請使用上一步取得的 URL 作為參數，執行此腳本：
```bash
python jules-scratch/verification/e2e_test.py $URL
```

**4. 確認結果**
預期會看到以下成功結果：
-   測試腳本執行成功，沒有任何錯誤。
-   輸出日誌中會顯示 `Response Status: 200`，表示網路請求成功，沒有 404 錯誤。
-   在 `jules-scratch/verification/` 目錄下會生成一張名為 `download_fix_verification.jpg` 的截圖。你可以使用 `read_image_file` 工具來查看它，確認畫面內容符合預期。

---

## Part 2: 後續建議開發項目
在確認現有功能穩定後，您可以與使用者討論並進行以下功能的開發：

**A. 完善下載器功能**
- **現狀**：目前只有 YouTube 下載器 (`youtube_downloader.py`) 使用了穩健的命令列模式。Google Drive 下載器 (`drive_downloader.py`) 仍直接使用 Python 函式庫，且兩者均缺少超時機制。
- **建議**：
    1.  重構 `drive_downloader.py`，改為使用 `gdown` 的命令列模式，並加入穩健的錯誤處理。
    2.  為 `youtube_downloader.py` 和 `drive_downloader.py` 的 `subprocess` 呼叫加入 `timeout` 參數，防止因單一檔案下載卡死而影響整個流程。

**B. 完善檔案命名機制**
- **現狀**：`標題_時間戳.副檔名` 的命名規則僅在最後生成 AI 報告時使用。
- **建議**：與使用者討論是否需要在**檔案被下載的當下**就立刻應用此命名規則，以方便檔案管理。

**C. 增加前端使用者回饋**
- **現狀**：目前僅在任務開始和結束時有狀態更新。
- **建議**：利用 WebSocket，在檔案下載和 AI 處理過程中，提供更即時、詳細的進度條或百分比更新，提升使用者體驗。

---

## Part 3: 開發流程與注意事項

- **依賴管理**：`requirements` 目錄下的依賴清單可能不完整。在新增功能時，如果遇到 `ModuleNotFoundError`，請記得檢查並將缺失的套件手動新增到對應的 `requirements` 檔案中（通常是 `requirements/core.txt`）。
- **啟動方式**：切記，直接執行 `src/core/orchestrator.py` 會因 Python 路徑問題而失敗。**必須**使用本計畫第一部分提供的 `PYTHONPATH=src ...` 指令來啟動伺服器。
- **溝通語言**：請全程使用**繁體中文**與使用者溝通。
