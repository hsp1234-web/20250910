import asyncio
import logging
import sys
from pathlib import Path

# --- 路徑修正與日誌設定 ---
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
DOWNLOAD_DIR = PROJECT_ROOT / "temp_downloads_for_analysis"

logging.basicConfig(level=logging.WARNING) # 我們只關心最終結果，將日誌等級設為 WARNING

# --- 匯入我們的服務模組 ---
from src.tools.universal_downloader import download_file
from src.tools.content_extractor import extract_content

# --- 測試目標 ---
TEST_URL = "https://drive.google.com/file/d/1ADg9NnB10z3qjnSZPOn6BLh_Fz8wjY9T/view?usp=sharing"

def get_text():
    """下載、提取並印出文件的原始文字內容。"""
    print("\n--- 2. 文件原始文本 (從 PDF 提取) ---\n")

    # 步驟 1: 下載
    success, downloaded_path, _ = download_file(TEST_URL, str(DOWNLOAD_DIR))
    if not success:
        print("錯誤：無法下載原始文件進行比對。")
        return

    # 步驟 2: 提取
    content_data = extract_content(downloaded_path, str(DOWNLOAD_DIR))
    if not content_data or not content_data.get("text"):
        print("錯誤：無法從文件中提取文字內容。")
        return

    # 步驟 3: 印出原始文本
    print(content_data["text"])

    # 步驟 4: 清理
    import shutil
    shutil.rmtree(DOWNLOAD_DIR)

if __name__ == "__main__":
    get_text()