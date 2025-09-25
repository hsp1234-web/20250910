# AI 模型微服務 (LLM Service)

這是一個基於 FastAPI 和 Ollama 的微服務，旨在提供一個與本地大型語言模型（LLM）互動的標準化介面。

## 核心功能

- **模型懶加載 (Lazy Loading)**: 服務在接收到請求時，才會檢查所需的模型是否存在於本地。如果模型不存在，它會**自動觸發下載**，下載完成後再進行推論。這避免了在服務啟動時載入所有大型模型，從而顯著加快了啟動速度並節省了初期記憶體使用。
- **動態模型選擇**: 使用者可以在每次請求中指定要使用的模型，提供了極大的靈活性。
- **標準化 API**: 提供簡單易用的 RESTful API 端點，方便與其他服務或前端應用程式整合。

## API 端點說明

### 健康檢查

檢查服務是否正在運行。

- **GET** `/ping`

**回應範例:**
```json
{
  "status": "ok",
  "message": "LLM Service is running."
}
```

### 列出本地模型

獲取當前 Ollama 環境中所有已下載的模型列表。

- **GET** `/models`

**回應範例:**
```json
[
  {
    "name": "qwen2:1.5b",
    "modified_at": "2024-09-24T23:00:00.000Z",
    "size": 934255712
  },
  {
    "name": "gemma2:2b",
    "modified_at": "2024-09-24T22:00:00.000Z",
    "size": 1600000000
  }
]
```

### 生成文字

這是服務的核心功能。提交一個提示詞（Prompt）和模型名稱，以獲取生成的回應。

- **POST** `/generate`

**請求主體 (Request Body):**
```json
{
  "model": "qwen2:1.5b",
  "prompt": "請用繁體中文解釋什麼是量子糾纏？"
}
```
- `model` (可選): 指定要使用的模型名稱。如果未提供，將使用預設模型 (`qwen2:1.5b`)。
- `prompt` (必需): 您希望模型處理的提示詞。

**`curl` 指令範例:**
```bash
curl -X POST "http://127.0.0.1:8001/generate" \
-H "Content-Type: application/json" \
-d '{
  "model": "qwen2:1.5b",
  "prompt": "請給我一段關於如何學習 Python 的建議。"
}'
```

**回應範例:**
```json
{
  "model": "qwen2:1.5b",
  "response_text": "學習 Python 的一個好方法是從基礎開始，例如變數、資料類型和迴圈。接著，可以嘗試解決一些簡單的程式設計問題，並逐步挑戰更複雜的專案。利用線上資源，如文件、教學影片和社群論壇，將會對您的學習過程大有裨益。"
}
```

## 如何啟動服務

1. **確保 Ollama 正在運行**: 此服務依賴於在背景運行的 Ollama 應用程式。

2. **安裝依賴套件**:
   在 `services/llm_service` 目錄下，執行：
   ```bash
   pip install -r requirements.txt
   ```

3. **啟動 FastAPI 服務**:
   同樣在 `services/llm_service` 目錄下，執行以下指令。服務將會在 `http://127.0.0.1:8001` 上啟動。
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8001
   ```