# 股票代號提取器 POC 成果報告 (plan14_poc.md)

## 1. POC 目標

在開發 `document_processor_service` 的過程中，我們發現其使用的本地 AI 模型 (`gemma2:2b`) 雖然在語意理解上表現良好，但在精確提取關鍵資訊（如股票代號）方面存在不足。

為了解決此問題，我們決定採用一個更穩健的「**混合模式 (Hybrid Approach)**」方案。本次概念驗證 (POC) 的核心目標即是：

**開發並驗證一個獨立的、非 AI 的微服務，用以準確、可靠地從任意文本中提取所有有效的台股股票代號。**

此 POC 的成功，將為把此功能整合回主要的 `document_processor_service` 提供堅實的技術基礎與信心。

## 2. 實作方案：非 AI 規則提取

我們採用了基於規則的純程式碼方案，以保證提取的絕對準確性。

### 2.1. 核心邏輯 (`extractor.py`)

1.  **尋找潛在代號**：使用正規表示式 `\b(\d{4})\b`，從輸入文字中找出所有格式為「四位數字」的獨立單詞。
2.  **載入代號列表**：利用 `twstock` 套件內建的台股代號列表 `twstock.codes`，並將其轉換為一個 `set` 集合，以實現高效查詢。
3.  **驗證與過濾**：遍歷所有找到的潛在代號，只保留那些確實存在於 `twstock.codes` 集合中的代號。
4.  **回傳結果**：回傳一個經過排序且不重複的、已驗證的有效股票代號列表。

### 2.2. 微服務架構

*   **框架**: 使用 FastAPI 建立一個輕量級的 Web 服務。
*   **API 端點**: 提供一個 `POST /api/extract_stock_ids` 端點，接收包含 `text` 欄位的 JSON 物件，並回傳一個包含股票代號的 JSON 陣列。

## 3. 測試與驗證

### 3.1. 單元測試

我們為 `extractor.py` 編寫了涵蓋多種邊界情況的 Pytest 單元測試，所有單元測試均 **100% 通過**，證明了核心邏輯的穩健性。

### 3.2. 端到端 POC 驗證

這是本次 POC 最關鍵的驗證步驟。我們成功啟動了 `stock_id_extractor_service` 微服務，並使用 `curl` 指令模擬真實的 API 呼叫。

#### 3.2.1. 驗證所使用的原始文本

我們使用了從「日月光投控」PDF 報告中提取的真實文本作為輸入：

```
小作文 日月光投控 3711 公司簡介 隸屬 電子–半導體 產業類別。資本額 441.53 億 日月光投資控股股份有限公司（以下稱本公司）於107 年4 月30 日設立於高雄楠梓科技 產業園區。所營業務主要為半導體、基板、電腦週邊設備及電子零配件之製造、組合、加 工、測試及銷售。 ...
```

#### 3.2.2. 驗證指令與回傳結果

**執行指令：**
```bash
curl -X POST "http://127.0.0.1:8002/api/extract_stock_ids" \
-H "Content-Type: application/json" \
-d '{"text": "小作文 日月光投控 3711 公司簡介..."}'
```

**服務實際回傳結果：**
```json
["3711"]
```

## 4. POC 結論

本次 POC 圓滿成功。驗證結果清楚地表明，我們新建立的、基於非 AI 技術的 `stock_id_extractor_service` 微服務，能夠**準確、可靠地**從一段真實的文件文本中，提取出關鍵的股票代號 **"3711"**。這成功地解決了原先純 AI 模型在精確資訊提取上的不足，並證明了「AI+規則」混合模式方案的卓越可行性。

## 5. 第二階段：整合至核心服務

在第一階段 POC 成功後，我們啟動了第二階段任務：將此高精準度的提取器邏輯，正式整合進核心的 `document_processor_service`。

### 5.1. 整合目標

我們採納了與使用者討論後確定的 **方案 A：串聯式 (Pipeline)**，旨在結合規則方法的「精準性」與 AI 模型的「分析深度」。

1.  **優先提取**：首先，使用本 POC 驗證過的高精準度「正規表示式 + twstock」提取器，從原始文本中找出所有股票代號。
2.  **輔助分析**：然後，將提取器的輸出（股票代號列表），連同原始文本，一起交給 AI 模型。
3.  **任務轉變**：AI 模型的任務從「從零開始提取」轉變為「基於已有的精準結果，進行更深層次的分析、摘要或關聯」。

### 5.2. 整合進度表 (含程式碼細節)

| 狀態 | 步驟 | 細節與程式碼片段 |
| :--- | :--- | :--- |
| ✅ | **1. 遷移提取器模組** | 將 `stock_id_extractor_service` 的核心邏輯 `extractor.py`，完整複製到 `document_processor_service` 中，成為一個新的本地模組 `stock_id_extractor.py`。 |
| ✅ | **2. 更新服務依賴** | 將 `twstock` 套件新增至根目錄的 `requirements.txt` 中，以確保其被標準安裝流程 `setup_environment.sh` 納入。 |
| ✅ | **3. 修改核心處理流程** | 修改 `processor.py` 的 `process_document_url` 函式，在呼叫 AI 分析前，先呼叫新的 `extract_stock_ids` 函式，實現「先提取，後分析」的串聯流程。<br>```python\n# processor.py 片段\nasync def process_document_url(source_url: str):\n    # ... (下載與內容提取) ...\n\n    # 步驟 3: 預先提取股票代號\n    log.info("...")\n    stock_ids = await asyncio.to_thread(extract_stock_ids, content_data["text"])\n\n    # 步驟 4: 使用本地 LLM 結合已提取的代號進行分析\n    log.info("...")\n    analysis_result = await analyze_text_with_llm(content_data["text"], stock_ids)\n\n    # ... (儲存結果) ...\n``` |
| ✅ | **4. 重新設計 AI 提示詞** | 大幅修改 `build_analysis_prompt` 函式，明確告知 AI 已知的股票代號列表，並要求它基於此列表進行分析，同時更新回傳的 JSON 格式。<br>```python\n# processor.py 片段\ndef build_analysis_prompt(text_content: str, stock_ids: list[str]) -> str:\n    if stock_ids:\n        stock_id_info = f"外部工具已經在文本中識別出以下台股股票代號：{stock_ids}。..."\n    else:\n        stock_id_info = "外部工具在文本中沒有找到任何台股股票代號。"\n\n    prompt = f\"\"\"\n你是一位專業、謹慎的金融市場分析師...\n--- 已知資訊 ---\n...2.  **預提取的股票代號**: {stock_id_info}\n...\n--- JSON 輸出指令 ---\n...2.  `analyzed_stock_ids`: (字串列表) {stock_id_instruction}\n...\"\"\"\n    return prompt\n``` |
| ✅ | **5. 編寫並執行整合測試** | 在 `test_processor.py` 中新增了一個端到端的整合測試案例。該測試使用「日月光投控」的真實文本，完整驗證了新的串聯式處理流程。<br>```python\n# test_processor.py 片段\n@pytest.mark.asyncio\nasync def test_process_document_url_integration_with_real_text(mocker):\n    # ... (設定模擬)\n    mock_analyze_llm = mocker.patch('...analyze_text_with_llm', ...)\n\n    await process_document_url(test_url)\n\n    # 核心斷言：驗證提取器的結果被正確傳遞\n    mock_analyze_llm.assert_called_once_with(REAL_TEST_TEXT, ["3711"])\n``` |
| ✅ | **6. 解決環境與依賴問題** | 在測試過程中，發現並徹底解決了專案環境設定的一系列深層次問題，包括補齊根 `requirements.txt` 中缺失的多個核心及測試依賴，並確保使用正確的 `setup_environment.sh` 腳本進行安裝。 |
| ✅ | **7. 最終驗證** | 所有 `pytest` 測試（共 17 項）全部通過，確認新功能整合成功，且未對現有功能造成迴歸。 |

### 5.3. 最終成果

本次整合任務圓滿成功。`document_processor_service` 現在已經具備了「規則提取」與「AI 分析」相結合的混合處理能力。這個經過完整測試驗證的新流程，為後續處理真實世界的複雜財經文件，奠定了更穩固、更可靠的基礎。

## 6. 附錄：詳細執行與除錯日誌

本次整合過程並非一帆風順。在「步驟 5：編寫並執行整合測試」期間，我們遭遇了一系列由環境設定和依賴管理引發的連鎖問題。將此除錯歷程記錄下來，對未來的工作極具價值。

### 6.1. 初步失敗：依賴地獄 (Dependency Hell)

在完成程式碼修改並首次執行 `pytest` 後，我們立刻遭遇了 `ModuleNotFoundError`。這個問題像俄羅斯套娃一樣，一環套一環：

1.  **`dateutil` 遺失**：最初的錯誤。我們嘗試將 `python-dateutil` 加入根目錄的 `requirements.txt` 並手動 `pip install`，但問題依舊。
    ```
    ModuleNotFoundError: No module named 'dateutil'
    ```
2.  **發現 `setup_environment.sh`**：經過一番探索，我們發現專案的標準安裝流程是執行 `setup_environment.sh` 腳本，它使用 `uv` 來安裝依賴。這揭示了我們手動安裝無效的原因。
3.  **發現「單一來源」原則**：執行標準安裝腳本後，我們發現 `gdown`, `twstock`, `filetype`, `PyMuPDF`, `python-pptx` 等套件依然遺失。這讓我們最終確認：**專案的依賴安裝唯一來源是根目錄的 `requirements.txt`**，所有分散在各服務中的 `requirements.txt` 都不會被自動處理。
4.  **解決方案**：我們採用了「執行測試 -> 發現錯誤 -> 補齊依賴 -> 重新執行安裝腳本」的循環，最終將所有必需的執行時期依賴 (`gdown`, `twstock`, `filetype`, `PyMuPDF`, `python-pptx`) 全部補齊到了根 `requirements.txt` 中。

### 6.2. 中期失敗：測試環境的陷阱

在解決了執行依賴後，測試仍然失敗，並揭露了更深層的問題：

1.  **`fixture 'mocker' not found`**：這個錯誤讓我們意識到，不僅僅是程式的執行依賴，**測試本身的依賴**（如 `pytest-mock` 和 `pytest-asyncio`）也必須被加入到根 `requirements.txt` 中，才能被標準安裝流程所識別。
    ```
    ERROR: fixture 'mocker' not found
    ```
2.  **`IndentationError`**：一個由於人為疏忽導致的 Python 縮排錯誤，提醒我們在修改程式碼時必須更加謹慎。
    ```
    IndentationError: unexpected indent
    ```
3.  **`TypeError: object MagicMock can't be used in 'await' expression`**：這是最微妙的一個錯誤。它發生在我們的整合測試中，因為我們對 `asyncio.to_thread` 的模擬不夠精確。我們最初的 `lambda` 模擬直接回傳了一個 `MagicMock` 物件，而 `await` 關鍵字無法作用於它。
4.  **解決方案**：我們將 `pytest-mock` 和 `pytest-asyncio` 加入了主依賴列表，修正了縮排錯誤，並用一個 `async def` 輔助函式來完美地模擬 `asyncio.to_thread` 的非同步行為，最終解決了這個 `TypeError`。
    ```python
    # test_processor.py 片段 - 關鍵修正
    async def sync_to_thread_mock(func, *args, **kwargs):
        return func(*args, **kwargs)
    mocker.patch('...asyncio.to_thread', new=sync_to_thread_mock)
    ```

### 6.3. 最終的勝利

在經歷了上述所有挑戰後，我們再次執行 `python -m pytest tests/`，所有 17 個測試案例終於全部通過。這場艱苦的除錯過程，讓我們對專案的環境設定和非同步測試機制，有了前所未有的深刻理解。