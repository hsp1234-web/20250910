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
from typing import Optional
# --- 路徑修正 ---
# 將專案的 src 目錄新增到 Python 的搜尋路徑中，以便找到 db 模組
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 本地匯入 ---
# 在路徑修正後，我們可以從 db 和 core 模組匯入
try:
    from db.database import get_db_connection
    from core.time_utils import get_current_taipei_time_iso
except ImportError as e:
    # This block is kept just in case, but the primary error was a missing dependency.
    print(f"無法匯入 url_extractor.py 的依賴項: {e}", file=sys.stderr)
    sys.exit(1)

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('url_extractor')

def parse_chat_log(text: str) -> list[dict]:
    """
    [簡易版] 從給定的文字中，提取所有 http/https 網址。
    為了讓測試流程可以繼續，此版本放棄了對作者和時間的複雜解析，
    只專注於提取最關鍵的網址資訊。

    :param text: 包含網址的來源文字。
    :return: 一個字典列表，每個字典包含 'date', 'time', 'author', 'url'。
    """
    # 網址: 匹配 http/https 開頭的 URL
    url_pattern = re.compile(r'https?://\S+')
    urls = url_pattern.findall(text)

    results = []
    for url in urls:
        # 清理可能跟在 URL 後面的非 URL 字元（例如中文句號）
        # 這裡我們假設 URL 不會包含非 ASCII 字元
        cleaned_url = re.match(r'^[!-~]+', url)
        if cleaned_url:
            results.append({
                'date': None,
                'time': None,
                'author': "未知作者",
                'url': cleaned_url.group(0)
            })

    log.info(f"從文字中解析出 {len(results)} 個網址。")
    return results


def extract_urls(text: str) -> list[str]:
    """
    [過渡時期函式]
    為了保持舊 API 的相容性，此函式現在會呼叫新的解析器，
    並只回傳網址列表。未來應直接使用 parse_chat_log。
    """
    log.warning("呼叫了過時的函式 extract_urls。請考慮切換到 parse_chat_log。")
    parsed_data = parse_chat_log(text)
    # 只回傳網址列表以維持舊的介面
    return [item['url'] for item in parsed_data]

def save_urls_to_db(parsed_data: list[dict], source_text: str, conn: Optional[sqlite3.Connection] = None):
    """
    [新版] 將解析後的結構化資料儲存到資料庫的 `extracted_urls` 資料表中。

    :param parsed_data: 一個包含字典的列表，每個字典應有 'url' 和 'author' 鍵。
    :param source_text: 這些網址的來源文字。
    :param conn: 一個可選的 sqlite3 Connection 物件。如果未提供，函式會自行管理連線。
    """
    if not parsed_data:
        log.info("沒有要儲存的資料，跳過資料庫操作。")
        return

    # 標記是否為內部管理的連線
    is_managed_locally = not conn
    db_conn = conn if conn else get_db_connection()

    if not db_conn:
        log.error("無法建立資料庫連線，資料儲存失敗。")
        return

    try:
        with db_conn:
            cursor = db_conn.cursor()
            created_at_iso = get_current_taipei_time_iso()

            # 準備要插入的多筆資料，現在包含作者、訊息日期和時間
            data_to_insert = [
                (item['url'], item['author'], item['date'], item['time'], source_text, created_at_iso)
                for item in parsed_data
            ]

            # 使用 executemany 來高效地插入多筆記錄
            cursor.executemany(
                "INSERT INTO extracted_urls (url, author, message_date, message_time, source_text, created_at, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                data_to_insert
            )
        log.info(f"成功將 {len(parsed_data)} 筆解析資料儲存到資料庫。")
    except sqlite3.Error as e:
        log.error(f"儲存解析資料到資料庫時發生錯誤: {e}", exc_info=True)
    finally:
        if is_managed_locally and db_conn:
            db_conn.close()

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
