# LINE 內容解析與匯出功能開發計畫 (plan12.md)

## 一、專案目標

本計畫旨在開發一個新功能，能夠解析格式不一但有規律的 LINE 聊天記錄，將其中有價值的「小作文」報告提取出來，進行結構化儲存，並提供多樣化的呈現、匯出與雲端同步選項，以提升資料處理效率。

## 二、功能模組與開發階段

我們將採用分階段的開發策略，確保每個功能的穩定性。

### **階段一：核心功能 - 解析、儲存與呈現**

此階段的目標是建立一個能將 LINE 文字轉換為資料庫紀錄的完整流程。

1.  **後端 - 資料庫擴充**:
    *   **任務**: 在現有的 SQLite 資料庫 (`database.sqlite3`) 中建立一個新的資料表，命名為 `essays`。
    *   **欄位設計**:
        *   `id`: INTEGER, PRIMARY KEY (主鍵)
        *   `submitted_at`: TIMESTAMP (原始提交時間)
        *   `submitter_raw`: TEXT (提交者資訊)
        *   `title`: TEXT (報告標題)
        *   `url`: TEXT, UNIQUE (文件連結，確保唯一性)
        *   `status`: TEXT (處理狀態，如 `pending`, `processed`)
        *   `source_text`: TEXT (原始訊息文字，供備查)
        *   `created_at`: TIMESTAMP (資料入庫時間)
    *   **執行檔案**: 修改 `src/db/initialize_database.py`。

2.  **前端 - 使用者介面**:
    *   **任務**: 建立一個新的 HTML 頁面 `line_parser.html`。
    *   **頁面元件**:
        *   一個大型文字區域 (`<textarea>`) 供使用者貼上 LINE 聊天記錄。
        *   一個「開始解析」按鈕。
        *   一個用來顯示結果的區域。

3.  **前後端整合**:
    *   **前端邏輯 (JavaScript)**: 編寫腳本以讀取輸入文字，根據時間、使用者名稱、「小作文」等關鍵字進行正規表示式 (RegEx) 解析，並將結構化後的資料打包成 JSON 格式。
    *   **後端 API**: 建立一個新的 API 端點 (例如 `/api/essays/upload`)，用於接收前端傳來的 JSON 資料，並將其寫入 `essays` 資料庫表。
    *   **資料呈現**: API 應能回傳目前資料庫中的所有 `essays` 紀錄，前端接收後以**表格 (Table)** 形式動態呈現在頁面上。

### **階段二：進階功能 - 匯出與視覺化**

在核心功能穩定後，擴充資料的應用性。

1.  **多格式匯出**:
    *   **任務**: 在 `line_parser.html` 頁面的表格旁，新增「匯出為 Excel」及「匯出為 PDF」按鈕。
    *   **技術方案**:
        *   **Excel**: 後端使用 `pandas` 或 `openpyxl` 函式庫，將 `essays` 表的資料轉換為 `.xlsx` 檔案供使用者下載。
        *   **PDF**: 後端使用 `reportlab` 函式庫，將資料格式化為專業的 PDF 報告。

2.  **視覺化呈現 - 圖卡 (Cards)**:
    *   **任務**: 在表格顯示模式外，提供一種「圖卡」顯示模式。
    *   **實作**: 每張圖卡對應一筆報告紀錄，清晰地展示標題、提交者、時間和文件連結，提供比表格更佳的視覺體驗。前端可設計一個切換按鈕在「表格」與「圖卡」模式間切換。

### **階段三：雲端整合 - Google Sheets 同步**

實現自動化的雲端備份與協作。

1.  **後端整合**:
    *   **任務**: 在後端整合 Google Sheets API。
    *   **依賴套件**: 安裝 `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`。
    *   **認證流程**: 實作 Google 的 OAuth 2.0 授權機制。這需要使用者在初次使用時，授權應用程式存取其 Google Sheets。系統會在本機安全地儲存 `credentials.json` 與 `token.json`。

2.  **前端觸發**:
    *   **任務**: 在頁面上新增「同步至 Google Sheets」按鈕。
    *   **執行流程**: 點擊後，觸發後端 API，後端將從 `essays` 資料庫讀取所有資料，並將其寫入使用者指定的 Google 試算表中。如果試算表或工作表不存在，系統應能自動建立。

## 三、交付成果

*   一個全新的前端頁面 (`line_parser.html`)。
*   修改後的資料庫初始化腳本 (`initialize_database.py`)。
*   新的後端 API 端點，用於處理資料的接收、儲存、查詢、匯出與同步。
*   所有程式碼註解、輸出訊息均使用繁體中文。

小作文範例

] 小作文天地的聊天記錄 儲存日期：2025/9/17 18:40

2025/4/3（週四） 14:36 069-0401669Crswin加入聊天 17:06 501-0723486Mason加入聊天 17:11 501-0723486Mason 四月小作文-0050元大台灣50 https://1drv.ms/u/s!AoaAyZHt1qThgRnnZPjmjLXlpMal?e=QtBZG4 17:13 502-0724579Cowboy加入聊天 17:13 502-0724579 Cowboy 四月小作文-來頡6799 https://drive.google.com/file/d/1RUl7XhxyJpxKO4RBX0AxeeyD4ABYPU_l/view?usp=sharing 17:54 500-0724304FOMO就剁手手加入聊天

2025/4/4（週五） 17:44 504-0718103Leo加入聊天 17:46 504-0718103Leo已收回訊息 17:46 504-0718103Leo 四月小作文-精確3162 https://docs.google.com/document/d/16TkL54YmFAToS1UR26VdV_mYgr8bCAml/edit?tab=t.0 17:48 505-0724540捲髮狼加入聊天 17:48 505-0724540捲髮狼 四月小作文-5515建國 https://drive.google.com/file/d/1dwnVczcEvhIIj5TOXRHVow876da6zAGp/view?usp=drivesdk

2025/4/5（週六） 12:21 383-0488695 三寶已收回訊息 12:21 383-0488695 三寶 小作文-2424隴華

這是第一種

2025/9/17 18:40

2025/4/3（週四） 14:36 069-0401669Crswin加入聊天 17:06 501-0723486Mason加入聊天 17:11 501-0723486Mason 四月小作文-0050元大台灣50 https://1drv.ms/u/s!AoaAyZHt1qThgRnnZPjmjLXlpMal?e=QtBZG4 17:13 502-0724579Cowboy加入聊天 17:13 502-0724579 Cowboy 四月小作文-來頡6799 https://drive.google.com/file/d/1RUl7XhxyJpxKO4RBX0AxeeyD4ABYPU_l/view?usp=sharing 17:54 500-0724304FOMO就剁手手加入聊天

2025/4/4（週五） 17:44 504-0718103Leo加入聊天 17:46 504-0718103Leo已收回訊息 17:46 504-0718103Leo 四月小作文-精確3162 https://docs.google.com/document/d/16TkL54YmFAToS1UR26VdV_mYgr8bCAml/edit?tab=t.0 17:48 505-0724540捲髮狼加入聊天 17:48 505-0724540捲髮狼 四月小作文-5515建國 https://drive.google.com/file/d/1dwnVczcEvhIIj5TOXRHVow876da6zAGp/view?usp=drivesdk

2025/4/5（週六） 12:21 383-0488695 三寶已收回訊息 12:21 383-0488695 三寶 小作文-2424隴華

https://docs.google.com/document/d/10nDGa7nWuSZCLhU9qtR_VW8Cx-yQllk5/edit?usp=drive_link&ouid=105443695704290227678&rtpof=true&sd=true 13:19 421-0299033青蛙狼 https://docs.google.com/document/d/1-OeWOZfZ8-KQb2-S-QhfthC7k-UPb4KofyzmLiGT17Y/edit 14:08 506-0723994 樂觀感恩加入聊天 14:08 503-0551726千千加入聊天 14:09 503-0551726千千 四月小作文-日月光投控 3711 https://drive.google.com/file/d/1ADg9NnB10z3qjnSZPOn6BLh_Fz8wjY9T/view?usp=sharing

這是第二種
