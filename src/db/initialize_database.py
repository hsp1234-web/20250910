# src/db/initialize_database.py
import sqlite3
import sys
from pathlib import Path

# --- 路徑設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

# --- 資料庫設定 ---
DB_DIR = Path(__file__).parent
DB_PATH = DB_DIR / "database.sqlite3"

# --- SQL 定義 ---
API_KEYS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_name TEXT NOT NULL UNIQUE,
    key_hash TEXT NOT NULL UNIQUE,
    key_value TEXT NOT NULL,
    key_type TEXT NOT NULL DEFAULT 'gemini', -- 'gemini' or 'fred'
    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'cooldown', 'disabled'
    last_used_at TIMESTAMP,
    cooldown_until TIMESTAMP,
    last_validated_at TIMESTAMP,
    is_valid BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    request_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    total_tokens_used INTEGER DEFAULT 0
);
"""

EXTRACTED_URLS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS extracted_urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE
);
"""

def _add_column_if_not_exists(cursor: sqlite3.Cursor, table_name: str, column_name: str, column_definition: str):
    """
    一個輔助函式，用於檢查欄位是否存在，如果不存在則新增。
    這使得腳本可以安全地在舊版資料庫上執行。
    """
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    if column_name not in columns:
        print(f"在 `{table_name}` 表中找不到 `{column_name}` 欄位，正在新增...")
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
        print(f"`{column_name}` 欄位已成功新增。")
    else:
        print(f"欄位 `{column_name}` 已存在於 `{table_name}` 表中，無需改動。")


def initialize():
    """
    初始化資料庫。
    1. 如果表格不存在，則建立一個包含所有最新欄位的新表格。
    2. 如果表格已存在，則檢查並新增缺失的欄位。
    """
    connection = None
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        print("步驟 1: 正在建立/更新 `api_keys` 資料表...")
        cursor.execute(API_KEYS_TABLE_SQL)
        _add_column_if_not_exists(cursor, 'api_keys', 'total_tokens_used', 'INTEGER DEFAULT 0')
        _add_column_if_not_exists(cursor, 'api_keys', 'key_type', "TEXT NOT NULL DEFAULT 'gemini'")

        print("\n步驟 2: 正在建立/更新 `extracted_urls` 資料表...")
        # 首先確保資料表存在 (至少有 id 和 url)
        cursor.execute(EXTRACTED_URLS_TABLE_SQL)

        # (Jules @ 2025-10-07) 核心修正：為所有欄位新增向下相容檢查，確保舊資料庫也能平滑升級
        _add_column_if_not_exists(cursor, 'extracted_urls', 'title', 'TEXT')
        _add_column_if_not_exists(cursor, 'extracted_urls', 'author', 'TEXT')
        _add_column_if_not_exists(cursor, 'extracted_urls', 'message_date', 'TEXT')
        _add_column_if_not_exists(cursor, 'extracted_urls', 'message_time', 'TEXT')
        _add_column_if_not_exists(cursor, 'extracted_urls', 'source_text', 'TEXT')
        _add_column_if_not_exists(cursor, 'extracted_urls', 'created_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        _add_column_if_not_exists(cursor, 'extracted_urls', 'status', "TEXT DEFAULT 'pending'")
        _add_column_if_not_exists(cursor, 'extracted_urls', 'source', "TEXT")

        # (Jules @ 2025-10-11) 新增 processing_history 欄位
        _add_column_if_not_exists(cursor, 'extracted_urls', 'processing_history', 'TEXT')
        # (Jules @ 2025-10-11) 新增其他後續流程所需的欄位
        _add_column_if_not_exists(cursor, 'extracted_urls', 'local_path', 'TEXT')
        _add_column_if_not_exists(cursor, 'extracted_urls', 'extracted_text', 'TEXT')
        _add_column_if_not_exists(cursor, 'extracted_urls', 'extracted_image_paths', 'TEXT')
        _add_column_if_not_exists(cursor, 'extracted_urls', 'last_error_details', 'TEXT')

        # (Jules @ 2025-10-11) 移除舊的、不再使用的狀態欄位
        # 注意：直接刪除欄位在 SQLite 中比較複雜，且可能造成資料遺失。
        # 在此開發階段，我們僅在程式邏輯中停止使用它們，並在初始化腳本中標註為待移除。
        # 若需要，可另外編寫一個遷移腳本來處理舊資料。
        # _remove_column_if_exists(cursor, 'extracted_urls', 'ocr_status')
        # _remove_column_if_exists(cursor, 'extracted_urls', 'ai_status')

        connection.commit()
        print(f"\n資料庫初始化/更新成功。資料庫檔案位於: {DB_PATH}")

    except sqlite3.Error as e:
        print(f"資料庫操作時發生錯誤: {e}", file=sys.stderr)
        if connection:
            connection.rollback()
    finally:
        if connection:
            connection.close()

if __name__ == "__main__":
    print("--- 正在執行資料庫初始化/更新腳本 ---")
    initialize()
    print("--- 腳本執行完畢 ---")