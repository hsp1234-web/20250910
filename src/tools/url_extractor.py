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
    (Jules @ 2025-09-17) 新版解析器
    從給定的 LINE 聊天紀錄文字中，解析出日期、時間、作者、標題和連結。
    這個實作採用區塊化處理，能夠正確處理跨多行的訊息。

    :param text: 包含 LINE 聊天紀錄的來源文字。
    :return: 一個字典列表，每個字典包含 'date', 'time', 'author', 'title', 'url'。
    """
    results = []
    current_date = None
    lines = text.split('\n')
    i = 0

    # 定義正規表示式
    date_pattern = re.compile(r'(\d{4})[年/](\d{1,2})[年/](\d{1,2})')
    message_pattern = re.compile(r'^(\d{2}:\d{2})\t([^\t]+)\t?(.*)$')
    url_pattern = re.compile(r'https?://\S+')

    while i < len(lines):
        line = lines[i].strip()

        # 1. 處理日期行
        date_match = date_pattern.match(line)
        if date_match:
            year, month, day = date_match.groups()
            current_date = f"{year}-{int(month):02d}-{int(day):02d}"
            i += 1
            continue

        if not current_date:
            i += 1
            continue

        # 2. 處理訊息行
        message_match = message_pattern.match(line)
        if message_match:
            time, author, first_line_content = message_match.groups()
            author = author.strip()

            # 過濾系統訊息
            if any(keyword in author for keyword in ["加入聊天", "退出聊天"]) or "已收回訊息" in first_line_content:
                i += 1
                continue

            # 收集完整的訊息區塊 (包含後續行)
            content_parts = [first_line_content.strip()]
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                # 檢查是否為區塊的結束標記
                if date_pattern.match(next_line) or message_pattern.match(next_line):
                    break

                # 如果不是結束標記，且不是空行，則加入內容
                if next_line:
                    content_parts.append(next_line)

                j += 1 # 繼續掃描下一行

            # 從訊息區塊中提取標題和 URL
            full_content_str = " ".join(content_parts)
            url_match = url_pattern.search(full_content_str)

            if url_match:
                url = url_match.group(0)
                # 標題是 URL 之前的所有文字
                title = full_content_str[:url_match.start()].strip()

                # 如果標題為空，使用一個預設值
                if not title:
                    title = "無標題"

                # 過濾掉教學/提醒訊息
                if "提醒小作文標題格式" in title:
                    i = j # 移動到下一個未處理的行
                    continue

                results.append({
                    'date': current_date,
                    'time': time,
                    'author': author,
                    'title': title,
                    'url': url
                })

            i = j # 移動到下一個未處理的行
        else:
            i += 1 # 如果不是訊息行，繼續下一行

    log.info(f"從聊天紀錄中解析出 {len(results)} 筆結構化資料。")
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

            # --- 步驟 1: 獲取資料庫中所有現存的 URL ---
            cursor.execute("SELECT url FROM extracted_urls")
            existing_urls = {row[0] for row in cursor.fetchall()}
            log.info(f"資料庫中已存在 {len(existing_urls)} 個獨立的網址。")

            # --- 步驟 2: 過濾掉已經存在的 URL ---
            new_items = []
            for item in parsed_data:
                if item['url'] not in existing_urls:
                    new_items.append(item)
                    existing_urls.add(item['url']) # 也加入到集合中，以處理當前批次內的重複

            if not new_items:
                log.info("所有解析出的網址都已存在於資料庫中，無需新增。")
                return

            log.info(f"過濾後，有 {len(new_items)} 筆新網址需要儲存。")

            # --- 步驟 3: 準備並插入新資料 ---
            created_at_iso = get_current_taipei_time_iso()
            data_to_insert = [
                (item['url'], item['author'], item['date'], item['time'], source_text, created_at_iso)
                for item in new_items
            ]

            cursor.executemany(
                "INSERT INTO extracted_urls (url, author, message_date, message_time, source_text, created_at, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                data_to_insert
            )
        log.info(f"成功將 {len(data_to_insert)} 筆新的解析資料儲存到資料庫。")
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
