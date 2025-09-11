# db/database.py
import sqlite3
import logging
import json
from pathlib import Path
import sys

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- 資料庫路徑設定 ---
DB_FILE = Path(__file__).parent / "tasks.db"

import os

def get_db_connection():
    """
    建立並回傳一個資料庫連線。
    在測試環境中，會優先使用 TEST_DB_PATH 環境變數指定的資料庫路徑。
    """
    db_path = os.environ.get("TEST_DB_PATH") or DB_FILE
    log.debug(f"正在連線到資料庫: {db_path}")
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        if db_path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
        return conn
    except sqlite3.Error as e:
        log.error(f"資料庫連線失敗: {e}")
        return None

def initialize_database(conn: sqlite3.Connection = None):
    """
    初始化資料庫。如果資料表不存在，就建立它們。
    """
    log.info(f"正在檢查並初始化資料庫...")
    close_conn_at_end = False
    if conn is None:
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        conn = get_db_connection()
        if not conn:
            log.critical("無法建立資料庫連線，初始化失敗。")
            return
        close_conn_at_end = True
        log.info(f"使用預設資料庫檔案: {DB_FILE}")

    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT '處理中',
                    progress INTEGER DEFAULT 0,
                    payload TEXT,
                    result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    type TEXT DEFAULT 'transcribe',
                    depends_on TEXT
                )
            """)
            migrations = {
                "progress": "INTEGER DEFAULT 0",
                "type": "TEXT DEFAULT 'transcribe'",
                "depends_on": "TEXT"
            }
            for col, col_type in migrations.items():
                try:
                    cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}")
                    log.info(f"欄位 '{col}' 已成功新增至 'tasks' 資料表。")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e):
                        pass
                    else:
                        raise
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON tasks (status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_id ON tasks (task_id)")
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS update_tasks_updated_at
                AFTER UPDATE ON tasks
                FOR EACH ROW
                BEGIN
                    UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
                END;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    source TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_source_level ON system_logs (source, level)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS update_app_state_updated_at
                AFTER UPDATE ON app_state FOR EACH ROW
                BEGIN
                    UPDATE app_state SET updated_at = CURRENT_TIMESTAMP WHERE key = OLD.key;
                END;
            """)
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS extracted_urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                source_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                status_message TEXT,
                local_path TEXT,
                file_hash TEXT,
                extracted_image_paths TEXT,
                extracted_text TEXT
            )
            ''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON extracted_urls (url)")
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url_id INTEGER,
                prompt_key TEXT,
                report_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_url_id) REFERENCES extracted_urls (id)
            )
            ''')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                source_document_id INTEGER,
                stage1_result_json TEXT,
                market_data_json TEXT,
                backtest_kpi_json TEXT,
                final_report_path TEXT,
                health_score REAL,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_document_id) REFERENCES extracted_urls (id)
            )
            ''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_analysis_status ON analysis_tasks (status)")
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS update_analysis_tasks_updated_at
                AFTER UPDATE ON analysis_tasks
                FOR EACH ROW
                BEGIN
                    UPDATE analysis_tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
                END;
            """)
            url_migrations = {
                "author": "TEXT",
                "message_date": "TEXT",
                "message_time": "TEXT",
                "status": "TEXT DEFAULT 'pending'",
                "status_message": "TEXT",
                "local_path": "TEXT",
                "file_hash": "TEXT",
                "extracted_image_paths": "TEXT",
                "extracted_text": "TEXT"
            }
            for col, col_type in url_migrations.items():
                try:
                    cursor.execute(f"ALTER TABLE extracted_urls ADD COLUMN {col} {col_type}")
                    log.info(f"欄位 '{col}' 已成功新增至 'extracted_urls' 資料表。")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e):
                        pass
                    else:
                        raise
        log.info("✅ 資料庫初始化完成。")
    except sqlite3.Error as e:
        log.error(f"初始化資料庫時發生錯誤: {e}")
    finally:
        if close_conn_at_end and conn:
            conn.close()

def set_app_state(key: str, value: str) -> bool:
    sql = "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)"
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn:
            conn.execute(sql, (key, value))
        log.info(f"✅ App state '{key}' 已更新。")
        return True
    except sqlite3.Error as e:
        log.error(f"❌ 更新 app_state '{key}' 時發生錯誤: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()

def get_app_state(key: str) -> str | None:
    sql = "SELECT value FROM app_state WHERE key = ?"
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (key,))
        row = cursor.fetchone()
        return row['value'] if row else None
    except sqlite3.Error as e:
        log.error(f"❌ 獲取 app_state '{key}' 時發生錯誤: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def add_task(task_id: str, payload: str, task_type: str = 'transcribe', depends_on: str = None) -> bool:
    sql = "INSERT INTO tasks (task_id, payload, status, type, depends_on) VALUES (?, ?, '處理中', ?, ?)"
    conn = get_db_connection()
    if not conn: return False
    log.info(f"DB:{DB_FILE} 準備新增 '{task_type}' 任務: {task_id} (依賴: {depends_on or '無'})")
    try:
        with conn:
            conn.execute(sql, (task_id, payload, task_type, depends_on))
        log.info(f"✅ 已成功新增任務到佇列: {task_id}")
        return True
    except sqlite3.IntegrityError:
        log.warning(f"⚠️ 嘗試新增一個已存在的任務 ID: {task_id}")
        return False
    except sqlite3.Error as e:
        log.error(f"❌ 新增任務 {task_id} 時發生資料庫錯誤: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()

def fetch_and_lock_task() -> dict | None:
    conn = get_db_connection()
    if not conn: return None
    log.debug(f"DB:{DB_FILE} Worker 正在嘗試獲取任務...")
    try:
        with conn:
            cursor = conn.cursor()
            sql = """
                SELECT id, task_id, payload, type
                FROM tasks
                WHERE status = '處理中' AND (
                    depends_on IS NULL OR
                    depends_on IN (SELECT task_id FROM tasks WHERE status = '已完成')
                )
                ORDER BY depends_on NULLS FIRST, created_at
                LIMIT 1
            """
            cursor.execute(sql)
            task = cursor.fetchone()
            if task:
                task_id_to_process = task["id"]
                log.info(f"🔒 找到並鎖定任務 ID: {task['task_id']} (資料庫 id: {task_id_to_process})")
                cursor.execute(
                    "UPDATE tasks SET status = 'processing' WHERE id = ?", (task_id_to_process,)
                )
                return dict(task)
            else:
                log.debug("...佇列為空，無待處理任務。")
                return None
    except sqlite3.Error as e:
        log.error(f"❌ 獲取並鎖定任務時發生錯誤: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def update_task_progress(task_id: str, progress: int, partial_result: str):
    result_payload = json.dumps({"transcript": partial_result})
    sql = "UPDATE tasks SET progress = ?, result = ? WHERE task_id = ?"
    conn = get_db_connection()
    if not conn: return
    try:
        with conn:
            conn.execute(sql, (progress, result_payload, task_id))
        log.debug(f"📈 任務 {task_id} 進度已更新為: {progress}%")
    except sqlite3.Error as e:
        log.error(f"❌ 更新任務 {task_id} 進度時出錯: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

def update_task_status(task_id: str, status: str, result: str = None):
    sql = "UPDATE tasks SET status = ?, result = ? WHERE task_id = ?"
    conn = get_db_connection()
    if not conn: return
    try:
        with conn:
            conn.execute(sql, (status, result, task_id))
        log.info(f"✅ 任務 {task_id} 狀態已更新為: {status}")
    except sqlite3.Error as e:
        log.error(f"❌ 更新任務 {task_id} 狀態時出錯: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

def get_task_status(task_id: str) -> dict | None:
    sql = "SELECT task_id, status, progress, type, payload, result, created_at, updated_at FROM tasks WHERE task_id = ?"
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (task_id,))
        task = cursor.fetchone()
        return dict(task) if task else None
    except sqlite3.Error as e:
        log.error(f"❌ 查詢任務 {task_id} 時發生錯誤: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def find_dependent_task(parent_task_id: str) -> str | None:
    sql = "SELECT task_id FROM tasks WHERE depends_on = ?"
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (parent_task_id,))
        task = cursor.fetchone()
        return task['task_id'] if task else None
    except sqlite3.Error as e:
        log.error(f"❌ 尋找依賴於 {parent_task_id} 的任務時出錯: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def are_tasks_active() -> bool:
    sql = "SELECT 1 FROM tasks WHERE status IN ('處理中', 'processing') LIMIT 1"
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        return cursor.fetchone() is not None
    except sqlite3.Error as e:
        log.error(f"❌ 檢查活動任務時發生錯誤: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()

def get_all_tasks() -> list[dict]:
    sql = "SELECT task_id, status, progress, type, payload, result, created_at, updated_at FROM tasks ORDER BY created_at DESC"
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        tasks = cursor.fetchall()
        return [dict(task) for task in tasks]
    except sqlite3.Error as e:
        log.error(f"❌ 獲取所有任務時發生錯誤: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()

def add_system_log(source: str, level: str, message: str) -> bool:
    sql = "INSERT INTO system_logs (source, level, message) VALUES (?, ?, ?)"
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn:
            conn.execute(sql, (source, level.upper(), message))
        return True
    except sqlite3.Error as e:
        print(f"CRITICAL: Failed to write system log to DB from source {source}. Error: {e}", file=sys.stderr)
        return False
    finally:
        if conn:
            conn.close()

def get_system_logs_by_filter(levels: list[str] = None, sources: list[str] = None) -> list[dict]:
    conn = get_db_connection()
    if not conn: return []
    try:
        sql = "SELECT timestamp, source, level, message FROM system_logs"
        conditions = []
        params = []
        levels = levels or []
        sources = sources or []
        if levels:
            conditions.append(f"level IN ({','.join(['?'] * len(levels))})")
            params.extend(level.upper() for level in levels)
        if sources:
            conditions.append(f"source IN ({','.join(['?'] * len(sources))})")
            params.extend(sources)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY timestamp ASC"
        cursor = conn.cursor()
        cursor.execute(sql, params)
        logs = cursor.fetchall()
        return [dict(log) for log in logs]
    except sqlite3.Error as e:
        log.error(f"❌ 獲取系統日誌時發生錯誤: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()

def clear_all_tasks():
    sql = "DELETE FROM tasks"
    conn = get_db_connection()
    if not conn:
        log.error("無法建立資料庫連線，清理任務失敗。")
        return False
    try:
        with conn:
            conn.execute(sql)
        log.info("✅ 已成功清空所有任務。")
        return True
    except sqlite3.Error as e:
        log.error(f"❌ 清理任務時發生錯誤: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()

def get_all_app_states() -> dict[str, str]:
    sql = "SELECT key, value FROM app_state"
    conn = get_db_connection()
    if not conn: return {}
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return {row['key']: row['value'] for row in rows}
    except sqlite3.Error as e:
        log.error(f"❌ 獲取所有 app_state 時發生錯誤: {e}", exc_info=True)
        return {}
    finally:
        if conn:
            conn.close()

def create_analysis_task(source_document_id: int) -> int | None:
    """
    在 analysis_tasks 資料表中建立一個新的分析任務。

    :param source_document_id: 來源文件的 ID。
    :return: 新建立的任務 ID，如果失敗則回傳 None。
    """
    sql = "INSERT INTO analysis_tasks (source_document_id, status) VALUES (?, 'PENDING')"
    conn = get_db_connection()
    if not conn: return None
    log.info(f"DB: 準備為文件 ID {source_document_id} 建立新的分析任務。")
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(sql, (source_document_id,))
            new_task_id = cursor.lastrowid
        log.info(f"✅ 已成功建立分析任務，ID: {new_task_id}")
        return new_task_id
    except sqlite3.Error as e:
        log.error(f"❌ 建立分析任務時發生資料庫錯誤: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def get_all_analysis_tasks() -> list[dict]:
    """
    獲取資料庫中所有分析任務的列表。

    :return: 一個包含所有任務字典的列表。
    """
    sql = "SELECT id, status, source_document_id, health_score, final_report_path, error_message, created_at, updated_at FROM analysis_tasks ORDER BY created_at DESC"
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        tasks = cursor.fetchall()
        # 將 Row 物件轉換為標準字典列表
        return [dict(task) for task in tasks]
    except sqlite3.Error as e:
        log.error(f"❌ 獲取所有分析任務時發生錯誤: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    # 直接執行此檔案時，會進行初始化
    initialize_database()
