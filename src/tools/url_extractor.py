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
except ImportError as e:
    # This block is kept just in case, but the primary error was a missing dependency.
    print(f"無法匯入 url_extractor.py 的依賴項: {e}", file=sys.stderr)
    sys.exit(1)

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('url_extractor')

def parse_chat_log(text: str) -> list[dict]:
    """
    從給定的 LINE 聊天紀錄文字中，解析出日期、時間、作者和連結。
    這個實作是根據使用者提供的聊天紀錄範例所設計。

    :param text: 包含 LINE 聊天紀錄的來源文字。
    :return: 一個字典列表，每個字典包含 'date', 'time', 'author', 'url'。
    """
    # 偵測 LINE 聊天紀錄中的關鍵模式
    # 1. 日期行: e.g., "2025/5/6（週二）"
    date_pattern = re.compile(r'(\d{4}/\d{1,2}/\d{1,2})（週.）')
    # 2. 發言行: e.g., "13:30\t579-0740320Jack" (後面可能還有文字)
    #    - \t 是定位字元 (tab)
    #    - 捕捉時間 (HH:MM) 和作者 (直到下一個 \t 或行尾)
    message_pattern = re.compile(r'^(\d{2}:\d{2})\t([^\t]+)')
    # 3. 網址: 匹配 http/https 開頭的 URL
    url_pattern = re.compile(r'https?://\S+')

    results = []
    current_date = None
    last_message_info = None

    lines = text.split('\n')

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        date_match = date_pattern.match(line)
        if date_match:
            # 將 YYYY/M/D 或 YYYY/MM/DD 格式標準化為 YYYY-MM-DD
            date_parts = date_match.group(1).split('/')
            current_date = f"{date_parts[0]}-{int(date_parts[1]):02d}-{int(date_parts[2]):02d}"
            last_message_info = None # 新的一天，重置作者資訊
            continue

        message_match = message_pattern.match(line)
        if message_match:
            time = message_match.group(1)
            author = message_match.group(2).strip().split('\t')[0] # 再一次確保只取作者名

            # 過濾掉無效的作者/系統訊息
            if any(keyword in author for keyword in ["加入聊天", "已收回訊息", "退出聊天"]):
                last_message_info = None
                continue

            # 暫存作者資訊，因為連結可能在下一行
            last_message_info = {'time': time, 'author': author}

            # 檢查發言的同一行是否包含網址
            url_match_in_line = url_pattern.search(line)
            if url_match_in_line:
                url = url_match_in_line.group(0)
                results.append({
                    'date': current_date,
                    'time': time,
                    'author': author,
                    'url': url
                })
                last_message_info = None # 處理完畢，重置以避免重複關聯
            continue

        # 如果這行不是日期也不是發言，檢查它是否只包含一個網址
        # 並且緊跟在一個有效的發言者之後
        # 使用 fullmatch 確保整行就是一個網址，避免誤判包含網址的普通句子
        url_match = url_pattern.fullmatch(line)
        if url_match and last_message_info:
            url = url_match.group(0)
            results.append({
                'date': current_date,
                'time': last_message_info['time'],
                'author': last_message_info['author'],
                'url': url
            })
            last_message_info = None # 處理完畢，重置

    log.info(f"從聊天紀錄中解析出 {len(results)} 筆有效的作者-網址配對。")
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

def save_urls_to_db(parsed_data: list[dict], source_text: str, conn: sqlite3.Connection):
    """
    [新版] 將解析後的結構化資料儲存到資料庫的 `extracted_urls` 資料表中。

    :param parsed_data: 一個包含字典的列表，每個字典應有 'url' 和 'author' 鍵。
    :param source_text: 這些網址的來源文字。
    :param conn: 一個有效的 sqlite3 Connection 物件。
    """
    if not parsed_data:
        log.info("沒有要儲存的資料，跳過資料庫操作。")
        return

    try:
        with conn:
            cursor = conn.cursor()
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
