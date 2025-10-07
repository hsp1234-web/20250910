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
DB_PATH = Path(__file__).resolve().parent.parent.parent / "src" / "db" / "database.sqlite3"

def _add_column_if_not_exists(cursor: sqlite3.Cursor, table_name: str, column_name: str, column_definition: str):
    """一個輔助函式，用於檢查欄位是否存在，如果不存在則新增。"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    if column_name not in columns:
        log.info(f"在 `{table_name}` 表中找不到 `{column_name}` 欄位，正在新增...")
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
        log.info(f"`{column_name}` 欄位已成功新增。")
    else:
        log.info(f"欄位 `{column_name}` 已在 `{table_name}` 表中，無需改動。")

def initialize_database():
    """
    [微服務自我修復]
    確保資料庫及 `extracted_urls` 表結構符合本服務的需求。
    此函式應在服務啟動時執行。
    """
    log.info("正在執行微服務的資料庫結構自我校驗...")
    if not DB_PATH.parent.exists():
        log.error(f"資料庫目錄不存在: {DB_PATH.parent}，無法繼續。")
        return

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 確保資料表存在
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS extracted_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE
                );
            """)
            # 確保所有需要的欄位都存在
            _add_column_if_not_exists(cursor, 'extracted_urls', 'title', 'TEXT')
            _add_column_if_not_exists(cursor, 'extracted_urls', 'author', 'TEXT')
            _add_column_if_not_exists(cursor, 'extracted_urls', 'message_date', 'TEXT')
            _add_column_if_not_exists(cursor, 'extracted_urls', 'source', 'TEXT')
            conn.commit()
            log.info("✅ 資料庫結構校驗完成。")
    except sqlite3.Error as e:
        log.error(f"資料庫自我校驗時發生嚴重錯誤: {e}", exc_info=True)


def get_db_connection() -> sqlite3.Connection:
    """建立並返回一個資料庫連線。"""
    try:
        return sqlite3.connect(DB_PATH, timeout=10)
    except sqlite3.Error as e:
        log.error(f"連線資料庫時發生錯誤: {e}", exc_info=True)
        raise

def parse_chat_log(text: str) -> List[Dict]:
    """
    從給定的 LINE 聊天紀錄文字中，解析出日期、時間、作者、標題和連結。
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
                results.append({'date': current_date, 'time': time, 'author': author, 'title': title, 'url': url})
            i = j
        else:
            i += 1
    log.info(f"從聊天紀錄中解析出 {len(results)} 筆結構化資料。")
    return results

def save_parsed_data_to_db(parsed_data: List[Dict]):
    """
    [微服務專用版本] 將解析後的資料儲存到資料庫。
    """
    if not parsed_data:
        log.info("沒有要儲存的資料。")
        return 0

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM extracted_urls")
            existing_urls = {row[0] for row in cursor.fetchall()}

            new_items = [item for item in parsed_data if item['url'] not in existing_urls]

            if not new_items:
                log.info("所有解析出的網址都已存在於資料庫中，無需新增。")
                return 0

            log.info(f"過濾後，有 {len(new_items)} 筆新資料需要儲存。")

            data_to_insert = [
                (item['url'], item['title'], item['author'], f"{item['date']} {item['time']}", 'essay_performance')
                for item in new_items
            ]

            cursor.executemany(
                """
                INSERT INTO extracted_urls (url, title, author, message_date, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                data_to_insert
            )
            inserted_count = cursor.rowcount
            conn.commit()
            log.info(f"成功將 {inserted_count} 筆新的解析資料儲存到資料庫。")
            return inserted_count
    except sqlite3.Error as e:
        log.error(f"儲存解析資料到資料庫時發生錯誤: {e}", exc_info=True)
        return 0