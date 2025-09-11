# src/tools/url_extractor.py
"""
這是一個命令列工具，用於從一段給定的文字中提取所有網址，
並將這些網址儲存到應用程式的 SQLite 資料庫中。

主要功能：
- 使用正規表示式從文字中尋找 http/https 網址。
- 連線到資料庫並將提取到的網址寫入 `extracted_urls` 資料表。
- 可作為獨立腳本透過命令列執行。
"""

import re
import argparse
import sys
import sqlite3
from pathlib import Path
import logging

# --- 路徑修正 ---
# 將專案的 src 目錄新增到 Python 的搜尋路徑中，以便找到 db 模組
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 本地匯入 ---
# 在路徑修正後，我們可以從 db 和 core 模組匯入
try:
    from db.database import get_db_connection
    from core.time_utils import get_current_taipei_time_iso
except ImportError:
    print("無法匯入模組。請確保路徑設定正確且 __init__.py 檔案存在。")
    sys.exit(1)

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('url_extractor')

def extract_urls(text: str) -> list[str]:
    """
    使用正規表示式從給定的文字中提取所有 http/https 網址。

    :param text: 要從中提取網址的來源文字。
    :return: 一個包含所有找到的網址的列表。
    """
    # 這個正規表示式匹配 http:// 或 https:// 開頭的網址
    # 它會匹配直到遇到空格、換行符或成為字串結尾
    url_pattern = re.compile(r'https?://\S+')
    urls = url_pattern.findall(text)
    log.info(f"從文字中提取了 {len(urls)} 個網址。")
    return urls

def save_urls_to_db(urls: list[str], source_text: str):
    """
    將網址列表儲存到資料庫的 `extracted_urls` 資料表中。

    :param urls: 要儲存的網址列表。
    :param source_text: 這些網址的來源文字。
    """
    if not urls:
        log.info("沒有要儲存的網址，跳過資料庫操作。")
        return

    conn = get_db_connection()
    if not conn:
        log.error("無法建立資料庫連線，網址儲存失敗。")
        return

    try:
        with conn:
            cursor = conn.cursor()
            # 獲取當前標準化的台北時間
            created_at_iso = get_current_taipei_time_iso()
            # 準備要插入的多筆資料，現在包含正確的時間戳
            data_to_insert = [(url, source_text, created_at_iso) for url in urls]
            # 使用 executemany 來高效地插入多筆記錄
            cursor.executemany(
                "INSERT INTO extracted_urls (url, source_text, created_at, status) VALUES (?, ?, ?, 'pending')",
                data_to_insert
            )
        log.info(f"成功將 {len(urls)} 個網址儲存到資料庫。")
    except sqlite3.Error as e:
        log.error(f"儲存網址到資料庫時發生錯誤: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="從文字中提取網址並儲存到資料庫。")
    parser.add_argument("text", type=str, help="包含網址的來源文字。")

    args = parser.parse_args()

    log.info("--- 開始執行 URL 提取工具 ---")

    # 步驟 1: 提取網址
    extracted = extract_urls(args.text)

    # 步驟 2: 儲存到資料庫
    if extracted:
        save_urls_to_db(extracted, args.text)
    else:
        log.info("在提供的文字中沒有找到任何網址。")

    log.info("--- URL 提取工具執行完畢 ---")
