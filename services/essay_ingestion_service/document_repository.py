import sqlite3
import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

# --- 日誌設定 ---
log = logging.getLogger(__name__)

# --- 資料庫路徑設定 ---
# JULES: 根據計畫，使用新的、獨立的資料庫檔案
DB_FILE = Path(__file__).parent / "line_analysis.sqlite3"

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
    初始化資料庫。如果 `analyzed_documents` 資料表不存在，則建立它。
    這個資料表專為新的文件分析功能設計。
    """
    log.info(f"正在檢查並初始化文件分析資料庫於: {DB_FILE}")
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn:
            cursor = conn.cursor()
            # JULES: 建立一個全新的資料表，包含所有需要的欄位，包括 image_paths_json
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analyzed_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_url TEXT NOT NULL UNIQUE,
                    summary TEXT,
                    analyzed_stock_ids_json TEXT, -- 儲存股票代號的 JSON 列表
                    strategy TEXT,
                    quality_score INTEGER,
                    is_trade_related TEXT,
                    image_paths_json TEXT, -- 儲存圖片路徑的 JSON 列表
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_url_analyzed ON analyzed_documents (source_url);")
            log.info("資料庫 `analyzed_documents` 資料表已成功初始化。")
    except sqlite3.Error as e:
        log.error(f"初始化 `analyzed_documents` 資料庫時發生錯誤: {e}", exc_info=True)
    finally:
        conn.close()

def update_task_status(source_url: str, status: str, error_message: Optional[str] = None):
    """
    為指定的 URL 建立或更新任務狀態。
    如果任務不存在，會先以 'pending' 狀態建立，然後再更新為指定狀態。
    """
    log.info(f"正在將 '{source_url}' 的任務狀態更新為 '{status}'...")
    conn = get_db_connection()
    if not conn:
        return

    try:
        with conn:
            cursor = conn.cursor()
            # JULES: 使用 INSERT OR IGNORE 確保紀錄存在，這簡化了上游邏輯
            cursor.execute("INSERT OR IGNORE INTO analyzed_documents (source_url) VALUES (?)", (source_url,))

            # 現在更新狀態
            cursor.execute("""
                UPDATE analyzed_documents
                SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE source_url = ?
            """, (status, error_message, source_url))
        log.info(f"成功更新 '{source_url}' 的任務狀態。")
    except sqlite3.Error as e:
        log.error(f"更新 '{source_url}' 任務狀態時發生錯誤: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

def save_successful_analysis(source_url: str, analysis_data: Dict[str, Any], image_paths: List[str]):
    """
    將成功的 AI 分析結果和圖片路徑列表儲存到資料庫。
    """
    log.info(f"準備將 '{source_url}' 的成功分析結果儲存到資料庫...")
    conn = get_db_connection()
    if not conn:
        return

    # JULES: 將 list 序列化為 JSON 字串以便儲存
    image_paths_json = json.dumps(image_paths, ensure_ascii=False)
    stock_ids_json = json.dumps(analysis_data.get('analyzed_stock_ids', []), ensure_ascii=False)

    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE analyzed_documents
                SET
                    summary = ?,
                    analyzed_stock_ids_json = ?,
                    strategy = ?,
                    quality_score = ?,
                    is_trade_related = ?,
                    image_paths_json = ?,
                    status = 'completed',
                    error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE
                    source_url = ?
            """, (
                analysis_data.get('summary'),
                stock_ids_json,
                analysis_data.get('strategy'),
                analysis_data.get('quality_score'),
                analysis_data.get('is_trade_related'),
                image_paths_json,
                source_url
            ))
        log.info(f"成功將 '{source_url}' 的分析結果與圖片路徑儲存到資料庫。")
    except sqlite3.Error as e:
        log.error(f"儲存 '{source_url}' 的分析結果時發生錯誤: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()