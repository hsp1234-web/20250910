# services/key_master_service/database.py
import sqlite3
import sys
import logging
from pathlib import Path
from typing import Optional, Any, Tuple

# --- 日誌設定 ---
# 設定一個基本的日誌記錄器，以便追蹤操作
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 資料庫設定 ---
# 將資料庫檔案放在服務自己的目錄下，確保獨立性
DB_PATH = Path(__file__).resolve().parent / "key_master.sqlite"

def get_db_connection() -> sqlite3.Connection:
    """建立並回傳一個資料庫連線。"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"無法連線到資料庫 {DB_PATH}: {e}", exc_info=True)
        raise

def _execute_query(query: str, params: Tuple = (), fetch: Optional[str] = None) -> Any:
    """
    執行資料庫查詢的統一輔助函式。
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)

        if fetch == 'one':
            return cursor.fetchone()
        elif fetch == 'all':
            return cursor.fetchall()
        else:
            conn.commit()
            return cursor.rowcount
    except sqlite3.Error as e:
        logger.error(f"資料庫錯誤: {e}\n查詢: {query}\n參數: {params}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

def create_db_and_tables():
    """
    建立資料庫檔案和 `api_keys` 資料表（如果它們不存在）。
    這個函式應該在 FastAPI 應用程式啟動時被呼叫。
    """
    sql_create_table = """
    CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key_name TEXT NOT NULL,
        key_type TEXT NOT NULL,
        key_hash TEXT NOT NULL UNIQUE,
        key_value TEXT NOT NULL,
        is_valid BOOLEAN DEFAULT 0,
        status TEXT DEFAULT 'active',
        last_validated_at TIMESTAMP,
        last_used_at TIMESTAMP,
        total_tokens_used INTEGER DEFAULT 0,
        request_count INTEGER DEFAULT 0
    );
    """
    try:
        logger.info(f"正在初始化資料庫於: {DB_PATH}")
        _execute_query(sql_create_table)
        logger.info("資料庫和資料表已成功驗證/建立。")
    except sqlite3.Error as e:
        logger.error(f"建立資料庫或資料表時發生錯誤: {e}", exc_info=True)
        raise