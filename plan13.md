# 計畫：建立 LINE 解析器微服務 (plan13.md)

## 一、開發目標

本計畫旨在將專案中現有的、成熟的 LINE 聊天記錄解析邏輯，重構成一個獨立、可測試、且高效的後端微服務。此舉將遵循微服務架構的最佳實踐，確保新功能的開發不影響現有系統的穩定性與啟動效率。

開發將遵循「後端優先、分段開發、可被測試」的原則。

## 二、後端開發階段 (優先執行)

**核心任務：將 `src/tools/url_extractor.py` 中的 `parse_chat_log` 函式，重構成一個完整的後端服務。**

1.  **建立微服務基礎架構**
    *   **任務**: 建立新目錄 `services/line_parser_service/`。
    *   **產出**: 在新目錄中建立標準化的模組檔案結構，包含：
        *   `main.py`: FastAPI 應用程式主進入點。
        *   `api_routes.py`: 定義所有 API 路由。
        *   `parser.py`: 存放核心解析邏輯。
        *   `repository.py`: 處理所有資料庫互動。
        *   `requirements.txt`: 列出此服務的所有 Python 相依套件 (如 `fastapi`, `uvicorn`, `pytest`)。

2.  **重構與遷移核心解析邏輯**
    *   **任務**: 將 `src/tools/url_extractor.py` 中，經過驗證的 `parse_chat_log` 函式，完整地遷移到新的 `services/line_parser_service/parser.py` 檔案中。
    *   **目標**: 將核心解析演算法與服務的其餘部分完全解耦，使其成為一個獨立、可單獨測試的純函式模組。

3.  **建立專屬資料庫與倉儲層 (Repository)**
    *   **任務**: 在 `repository.py` 中建立與資料庫互動的所有邏輯。
    *   **資料庫初始化**: 編寫一個 `initialize_database` 函式，此函式會在新服務自己的、獨立的 `line_parser.sqlite3` 資料庫中，建立 `essays` 資料表。資料表結構將參考 `plan12.md` 的設計。
    *   **資料儲存邏輯**: 改寫 `url_extractor.py` 中的 `save_urls_to_db` 函式，使其適應新的倉儲層設計，並將 `parse_chat_log` 解析出的結構化資料，儲存到新的 `essays` 資料表中。

4.  **建立 API 端點**
    *   **任務**: 在 `api_routes.py` 中，使用 FastAPI 框架建立所有後端 API。
    *   **端點設計**:
        *   `POST /api/essays/upload`: 接收前端傳來的純文字聊天記錄。此端點將依序呼叫解析器 (`parser.py`) 和倉儲層 (`repository.py`)，完成資料的解析與儲存。
        *   `GET /api/essays`: 從 `line_parser.sqlite3` 資料庫讀取所有已儲存的報告，並以 JSON 格式回傳給前端。

5.  **編寫後端 Pytest 測試**
    *   **任務**: 建立 `tests/test_line_parser_service/` 目錄，用於存放所有與新服務相關的測試。
    *   **單元測試 (`test_parser.py`)**: 編寫測試案例，使用下文提供的範例資料，直接對 `parser.py` 中的 `parse_chat_log` 函式進行測試，確保其在遷移後，對於不同格式的輸入依然能產出正確的結構化資料。
    *   **整合測試 (`test_api.py`)**: 使用 FastAPI 的 `TestClient`，對 `POST /api/essays/upload` 和 `GET /api/essays` 兩個 API 端點進行功能測試，驗證從接收請求、解析、儲存到查詢的完整後端流程皆能正常運作。

## 三、小作文範例 (用於測試與開發)

以下為兩種在真實世界中觀察到的 LINE 聊天記錄格式，將作為開發與測試期間的主要輸入範例。

### 範例格式一

```
] 小作文天地的聊天記錄 儲存日期：2025/9/17 18:40

2025/4/3（週四）
14:36 069-0401669Crswin加入聊天
17:06 501-0723486Mason加入聊天
17:11 501-0723486Mason 四月小作文-0050元大台灣50 https://1drv.ms/u/s!AoaAyZHt1qThgRnnZPjmjLXlpMal?e=QtBZG4
17:13 502-0724579Cowboy加入聊天
17:13 502-0724579 Cowboy 四月小作文-來頡6799 https://drive.google.com/file/d/1RUl7XhxyJpxKO4RBX0AxeeyD4ABYPU_l/view?usp=sharing
17:54 500-0724304FOMO就剁手手加入聊天

2025/4/4（週五）
17:44 504-0718103Leo加入聊天
17:46 504-0718103Leo已收回訊息
17:46 504-0718103Leo 四月小作文-精確3162 https://docs.google.com/document/d/16TkL54YmFAToS1UR26VdV_mYgr8bCAml/edit?tab=t.0
17:48 505-0724540捲髮狼加入聊天
17:48 505-0724540捲髮狼 四月小作文-5515建國 https://drive.google.com/file/d/1dwnVczcEvhIIj5TOXRHVow876da6zAGp/view?usp=drivesdk

2025/4/5（週六）
12:21 383-0488695 三寶已收回訊息
12:21 383-0488695 三寶 小作文-2424隴華
```

### 範例格式二 (訊息與連結可能分多行)

```
2025/9/17 18:40

2025/4/3（週四）
14:36 069-0401669Crswin加入聊天
17:06 501-0723486Mason加入聊天
17:11 501-0723486Mason 四月小作文-0050元大台灣50 https://1drv.ms/u/s!AoaAyZHt1qThgRnnZPjmjLXlpMal?e=QtBZG4
17:13 502-0724579Cowboy加入聊天
17:13 502-0724579 Cowboy 四月小作文-來頡6799 https://drive.google.com/file/d/1RUl7XhxyJpxKO4RBX0AxeeyD4ABYPU_l/view?usp=sharing
17:54 500-0724304FOMO就剁手手加入聊天

2025/4/4（週五）
17:44 504-0718103Leo加入聊天
17:46 504-0718103Leo已收回訊息
17:46 504-0718103Leo 四月小作文-精確3162 https://docs.google.com/document/d/16TkL54YmFAToS1UR26VdV_mYgr8bCAml/edit?tab=t.0
17:48 505-0724540捲髮狼加入聊天
17:48 505-0724540捲髮狼 四月小作文-5515建國 https://drive.google.com/file/d/1dwnVczcEvhIIj5TOXRHVow876da6zAGp/view?usp=drivesdk

2025/4/5（週六）
12:21 383-0488695 三寶已收回訊息
12:21 383-0488695 三寶 小作文-2424隴華
https://docs.google.com/document/d/10nDGa7nWuSZCLhU9qtR_VW8Cx-yQllk5/edit?usp=drive_link&ouid=105443695704290227678&rtpof=true&sd=true
13:19 421-0299033青蛙狼 https://docs.google.com/document/d/1-OeWOZfZ8-KQb2-S-QhfthC7k-UPb4KofyzmLiGT17Y/edit
14:08 506-0723994 樂觀感恩加入聊天
14:08 503-0551726千千加入聊天
14:09 503-0551726千千 四月小作文-日月光投控 3711 https://drive.google.com/file/d/1ADg9NnB10z3qjnSZPOn6BLh_Fz8wjY9T/view?usp=sharing
```