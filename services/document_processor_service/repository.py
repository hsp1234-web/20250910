import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, Any

# --- 日誌設定 ---
log = logging.getLogger(__name__)

# --- 資料庫路徑設定 ---
# 將資料庫檔案放在服務自己的目錄下，確保獨立性
DB_FILE = Path(__file__).parent / "document_processor.sqlite3"

def get_db_connection() -> Optional[sqlite3.Connection]:
    """建立並回傳一個 SQLite 資料庫連線。"""
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        log.error(f"無法連線到資料庫 {DB_FILE}: {e}", exc_info=True)
        return None

def initialize_database():
    """
    初始化資料庫。如果 `processed_documents` 資料表不存在，則建立它。
    """
    log.info(f"正在檢查並初始化資料庫於: {DB_FILE}")
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn:
            cursor = conn.cursor()
            # 建立資料表，欄位符合 plan14.md 的定義，並增加狀態追蹤欄位
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_url TEXT NOT NULL UNIQUE,
                    summary TEXT,
                    stock_id TEXT,
                    strategy TEXT,
                    quality_score INTEGER,
                    is_trade_related TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # 建立索引以加速 source_url 的查詢
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_url ON processed_documents (source_url);")
            log.info("資料庫 `processed_documents` 資料表已成功初始化。")
    except sqlite3.Error as e:
        log.error(f"初始化資料庫時發生錯誤: {e}", exc_info=True)
    finally:
        conn.close()

def create_processing_task(source_url: str) -> bool:
    """
    為一個新的 URL 在資料庫中建立一個處理中任務，狀態為 'pending'。
    如果 URL 已存在，則不進行任何操作。

    :param source_url: 要處理的文件的原始 URL。
    :return: 如果成功建立新任務則回傳 True，否則回傳 False。
    """
    log.info(f"正在為 '{source_url}' 建立處理任務...")
    conn = get_db_connection()
    if not conn:
        return False

    try:
        with conn:
            cursor = conn.cursor()
            # 使用 INSERT OR IGNORE 避免因為 UNIQUE 限制而發生錯誤
            cursor.execute("INSERT OR IGNORE INTO processed_documents (source_url, status) VALUES (?, 'pending')", (source_url,))
            if cursor.rowcount > 0:
                log.info(f"已為 '{source_url}' 成功建立新的處理任務。")
                return True
            else:
                log.warning(f"任務 '{source_url}' 已存在於資料庫中，跳過建立。")
                return False
    except sqlite3.Error as e:
        log.error(f"為 '{source_url}' 建立處理任務時發生錯誤: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()

def update_task_status(source_url: str, status: str, error_message: Optional[str] = None):
    """
    更新指定任務的狀態，主要用於標記處理中或失敗狀態。

    :param source_url: 任務的 URL。
    :param status: 新的狀態 (e.g., 'processing', 'failed')。
    :param error_message: 如果任務失敗，附上錯誤訊息。
    """
    log.info(f"正在將 '{source_url}' 的狀態更新為 '{status}'...")
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE processed_documents
                SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE source_url = ?
            """, (status, error_message, source_url))
        log.info(f"成功更新 '{source_url}' 的狀態。")
    except sqlite3.Error as e:
        log.error(f"更新 '{source_url}' 的狀態時發生錯誤: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

def save_successful_analysis(source_url: str, analysis_data: Dict[str, Any]):
    """
    將成功的 AI 分析結果儲存到資料庫，並將狀態更新為 'completed'。

    :param source_url: 文件的原始 URL。
    :param analysis_data: 一個包含分析結果的字典。
    """
    log.info(f"準備將 '{source_url}' 的成功分析結果儲存到資料庫...")
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE processed_documents
                SET
                    summary = ?,
                    stock_id = ?,
                    strategy = ?,
                    quality_score = ?,
                    is_trade_related = ?,
                    status = 'completed',
                    error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE
                    source_url = ?
            """, (
                analysis_data.get('summary'),
                analysis_data.get('stock_id'),
                analysis_data.get('strategy'),
                analysis_data.get('quality_score'),
                analysis_data.get('is_trade_related'),
                source_url
            ))
        log.info(f"成功將 '{source_url}' 的分析結果儲存到資料庫。")
    except sqlite3.Error as e:
        log.error(f"儲存分析結果到資料庫時發生錯誤: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()