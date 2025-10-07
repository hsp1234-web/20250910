# services/essay_ingestion_service/logic.py
import re
import sqlite3
import sys
from pathlib import Path
import logging
from typing import Optional, List, Dict

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger('essay_ingestion_service')

# --- 資料庫路徑 ---
# 這個微服務將直接存取主資料庫
DB_PATH = Path(__file__).resolve().parent.parent.parent / "src" / "db" / "database.sqlite3"

def get_db_connection():
    """建立並返回一個資料庫連線。"""
    try:
        # 檢查資料庫檔案是否存在
        if not DB_PATH.exists():
            log.error(f"資料庫檔案不存在於預期路徑: {DB_PATH}")
            return None
        return sqlite3.connect(DB_PATH, timeout=10)
    except sqlite3.Error as e:
        log.error(f"連線資料庫時發生錯誤: {e}", exc_info=True)
        return None

def parse_chat_log(text: str) -> List[Dict]:
    """
    從給定的 LINE 聊天紀錄文字中，解析出日期、時間、作者、標題和連結。
    這個實作採用區塊化處理，能夠正確處理跨多行的訊息。
    (Jules @ 2025-10-07: 從 src/tools/url_extractor.py 複製而來，保持解耦)

    :param text: 包含 LINE 聊天紀錄的來源文字。
    :return: 一個字典列表，每個字典包含 'date', 'time', 'author', 'title', 'url'。
    """
    results = []
    current_date = None
    lines = text.split('\n')
    i = 0

    date_pattern = re.compile(r'(\d{4}[./]\d{1,2}[./]\d{1,2}).*')
    message_pattern = re.compile(r'^(\d{2}:\d{2})[\t\s]+([^\t\s].*?)[\t\s]+(.*)$')
    url_pattern = re.compile(r'https?://\S+')

    while i < len(lines):
        line = lines[i].strip()

        date_match = date_pattern.match(line)
        if date_match:
            raw_date_str = date_match.group(1)
            normalized_date_str = re.sub(r'[./]', '-', raw_date_str)
            date_parts = normalized_date_str.split('-')
            current_date = f"{date_parts[0]}-{int(date_parts[1]):02d}-{int(date_parts[2]):02d}"
            i += 1
            continue

        if not current_date:
            i += 1
            continue

        message_match = message_pattern.match(line)
        if message_match:
            time, author, first_line_content = message_match.groups()
            author = author.strip()

            if any(keyword in author for keyword in ["加入聊天", "退出聊天"]) or "已收回訊息" in first_line_content:
                i += 1
                continue

            content_parts = [first_line_content.strip()]
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if date_pattern.match(next_line) or message_pattern.match(next_line):
                    break
                if next_line:
                    content_parts.append(next_line)
                j += 1

            full_content_str = " ".join(content_parts)
            url_match = url_pattern.search(full_content_str)

            if url_match:
                url = url_match.group(0)
                title_raw = full_content_str[:url_match.start()]
                title = re.sub(r'\s+', ' ', title_raw).strip() or "無標題"

                if "提醒小作文標題格式" in title:
                    i = j
                    continue

                results.append({
                    'date': current_date,
                    'time': time,
                    'author': author,
                    'title': title,
                    'url': url
                })

            i = j
        else:
            i += 1

    log.info(f"從聊天紀錄中解析出 {len(results)} 筆結構化資料。")
    return results

def save_parsed_data_to_db(parsed_data: List[Dict]):
    """
    [微服務專用版本]
    將解析後的結構化資料儲存到資料庫的 `extracted_urls` 資料表中，
    並將 `source` 欄位固定為 'essay_performance'。

    :param parsed_data: 一個包含字典的列表。
    :return: 成功插入的筆數。
    """
    if not parsed_data:
        log.info("沒有要儲存的資料。")
        return 0

    conn = get_db_connection()
    if not conn:
        log.error("無法建立資料庫連線，儲存操作終止。")
        return 0

    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM extracted_urls")
            existing_urls = {row[0] for row in cursor.fetchall()}
            log.info(f"資料庫中已存在 {len(existing_urls)} 個獨立的網址。")

            new_items = [item for item in parsed_data if item['url'] not in existing_urls]

            if not new_items:
                log.info("所有解析出的網址都已存在於資料庫中，無需新增。")
                return 0

            log.info(f"過濾後，有 {len(new_items)} 筆新資料需要儲存。")

            # (Jules @ 2025-10-07) 核心修改：在 INSERT 語句中加入 'source' 欄位
            data_to_insert = [
                (
                    item['url'],
                    item['title'],
                    item['author'],
                    f"{item['date']} {item['time']}", # 將日期和時間合併
                    'essay_performance' # 固定 source
                )
                for item in new_items
            ]

            # (Jules @ 2025-10-07) 核心修改：更新 INSERT 語句以匹配新結構
            cursor.executemany(
                """
                INSERT INTO extracted_urls (url, title, author, message_date, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                data_to_insert
            )
            inserted_count = cursor.rowcount
            log.info(f"成功將 {inserted_count} 筆新的解析資料儲存到資料庫。")
            return inserted_count
    except sqlite3.IntegrityError as e:
        log.warning(f"儲存資料時發生唯一性約束衝突，可能是併發請求導致: {e}")
        return 0
    except sqlite3.Error as e:
        log.error(f"儲存解析資料到資料庫時發生錯誤: {e}", exc_info=True)
        return 0
    finally:
        if conn:
            conn.close()