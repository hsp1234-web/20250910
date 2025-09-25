# 工具說明文件 (v2)

**文件狀態**: 手動撰寫 - 2025-09-09
**撰寫者**: Jules (AI 代理)

本文件旨在詳細說明 `src/tools/` 目錄下所有核心工具的功能、使用方式與依賴性。

---

### `url_extractor.py`

*   **功能簡介 (Functionality)**
    *   一個命令列工具，用於從一段給定的文字中提取所有網址，並將這些網址儲存到應用程式的 SQLite 資料庫中。

*   **主要函式 (Main Functions)**
    *   `extract_urls(text: str) -> list[str]`: 使用正規表示式從輸入文字中提取所有 http/https 網址。
    *   `save_urls_to_db(urls: list[str], source_text: str)`: 將提取到的網址列表存入資料庫的 `extracted_urls` 資料表中。

*   **使用方式 (Usage)**
    *   此工具可從命令列獨立執行，接收一段文字作為參數。
    ```bash
    python src/tools/url_extractor.py "這是一段包含 https://example.com 網址的文字。"
    ```

*   **依賴性 (Dependencies)**
    *   內部依賴: `src/db/database.py` 中的 `get_db_connection` 函式。
    *   資料庫: 需要存取 `tasks.db` 檔案中的 `extracted_urls` 資料表。

---

### `readme_tool.py`

*   **功能簡介 (Functionality)**
    *   一個自動化工具，用於掃描 `src/tools/` 目錄並根據每個工具的模組級 docstring 生成一份 Markdown 格式的說明文件。

*   **主要函式 (Main Functions)**
    *   `get_module_docstring(filepath: Path) -> str | None`: 使用 `ast` 模組安全地解析一個 Python 檔案並回傳其 docstring。
    *   `generate_tools_readme()`: 執行掃描、解析和寫入檔案的完整流程。

*   **使用方式 (Usage)**
    *   直接執行此腳本即可在專案根目錄生成或更新 `TOOLS_README.md`。
    ```bash
    python src/tools/readme_tool.py
    ```

*   **依賴性 (Dependencies)**
    *   無外部套件依賴。
    *   會讀取 `src/tools/` 目錄下的所有 `.py` 檔案。

---

### `drive_downloader.py`

*   **功能簡介 (Functionality)**
    *   一個專門用來處理 Google Drive 連結的下載工具，能夠將 Google Docs 或直接分享的檔案下載為 PDF。

*   **主要函式 (Main Functions)**
    *   `download_file(url: str, output_dir: str, file_name: str)`: 主要的下載函式。

*   **使用方式 (Usage)**
    *   通常由 `scripts/run_processing_pipeline.py` 腳本呼叫。

*   **依賴性 (Dependencies)**
    *   可能需要 `requests` 或其他 HTTP 客戶端套件 (需檢查原始碼確認)。

---

### `pdf_parser.py`

*   **功能簡介 (Functionality)**
    *   使用 `PyMuPDF` 套件來解析 PDF 檔案，提取其中的文字內容和所有內嵌的圖片。

*   **主要函式 (Main Functions)**
    *   `parse_pdf(pdf_path: str, image_output_dir: str)`: 解析指定的 PDF，將圖片存到指定目錄，並回傳文字內容與圖片路徑。

*   **使用方式 (Usage)**
    *   通常由 `scripts/run_processing_pipeline.py` 腳本呼叫。

*   **依賴性 (Dependencies)**
    *   外部套件: `PyMuPDF` (fitz)。

---

### `report_generator.py`

*   **功能簡介 (Functionality)**
    *   一個強大的報告產生器，能將文字和圖片組合成 HTML，並使用 `weasyprint` 轉為高品質的 PDF 報告。內建中文字體解決方案。

*   **主要函式 (Main Functions)**
    *   `setup_font()`: 自動下載並安裝 `Noto Sans TC` 字體到系統中，以解決 PDF 中文亂碼問題。
    *   `generate_pdf_report(data: dict, output_path: str)`: 根據輸入的資料產生最終的 PDF 報告。

*   **使用方式 (Usage)**
    *   通常由 `scripts/run_processing_pipeline.py` 腳本呼叫。

*   **依賴性 (Dependencies)**
    *   外部套件: `weasyprint`。
    *   系統權限: `setup_font()` 可能需要 `sudo` 權限來安裝字體。

---

### `gemini_manager.py`

*   **功能簡介 (Functionality)**
    *   作為與 Google Gemini API 溝通的統一介面，封裝了 API 金鑰管理、文字分析和圖片描述等功能。

*   **主要函式 (Main Functions)**
    *   `analyze_text(text: str)`: 呼叫 AI 進行文字摘要與關鍵字提取。
    *   `describe_image(image_path: str)`: 呼叫 AI 進行圖片內容描述。

*   **使用方式 (Usage)**
    *   在使用前需要先用 API 金鑰初始化 `GeminiManager` 類別。

*   **依賴性 (Dependencies)**
    *   外部套件: `google-generativeai`。
    *   需要有效的 Google API 金鑰。
