# db/database.py
import sqlite3
import logging
import json
from pathlib import Path

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
            # ... (table creation logic remains the same) ...
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL UNIQUE,
                    task_name TEXT,
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
            migrations = {"progress": "INTEGER DEFAULT 0", "type": "TEXT DEFAULT 'transcribe'", "depends_on": "TEXT", "task_name": "TEXT"}
            for col, col_type in migrations.items():
                try:
                    cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}")
                    log.info(f"欄位 '{col}' 已成功新增至 'tasks' 資料表。")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e): pass
                    else: raise
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON tasks (status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_id ON tasks (task_id)")
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS update_tasks_updated_at
                AFTER UPDATE ON tasks FOR EACH ROW
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
        log.info("✅ 資料庫初始化完成。")
    except sqlite3.Error as e:
        log.error(f"初始化資料庫時發生錯誤: {e}")
    finally:
        if close_conn_at_end and conn:
            conn.close()

def set_app_state(conn: sqlite3.Connection, key: str, value: str) -> bool:
    sql = "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)"
    try:
        conn.execute(sql, (key, value))
        log.info(f"✅ App state '{key}' 已更新。")
        return True
    except sqlite3.Error as e:
        log.error(f"❌ 更新 app_state '{key}' 時發生錯誤: {e}", exc_info=True)
        return False

def get_app_state(conn: sqlite3.Connection, key: str) -> str | None:
    sql = "SELECT value FROM app_state WHERE key = ?"
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (key,))
        row = cursor.fetchone()
        return row['value'] if row else None
    except sqlite3.Error as e:
        log.error(f"❌ 獲取 app_state '{key}' 時發生錯誤: {e}", exc_info=True)
        return None

def add_task(conn: sqlite3.Connection, task_id: str, payload: str, task_type: str = 'transcribe', task_name: str = None, depends_on: str = None) -> bool:
    sql = "INSERT INTO tasks (task_id, payload, status, type, task_name, depends_on) VALUES (?, ?, '處理中', ?, ?, ?)"
    log.info(f"準備新增 '{task_type}' 任務: {task_id} (名稱: {task_name or '未提供'}, 依賴: {depends_on or '無'})")
    try:
        conn.execute(sql, (task_id, payload, task_type, task_name, depends_on))
        log.info(f"✅ 已成功新增任務到佇列: {task_id}")
        return True
    except sqlite3.IntegrityError:
        log.warning(f"⚠️ 嘗試新增一個已存在的任務 ID: {task_id}")
        return False
    except sqlite3.Error as e:
        log.error(f"❌ 新增任務 {task_id} 時發生資料庫錯誤: {e}", exc_info=True)
        return False

def fetch_and_lock_task(conn: sqlite3.Connection) -> dict | None:
    log.debug(f"DB:{DB_FILE} Worker 正在嘗試獲取任務...")
    try:
        cursor = conn.cursor()
        sql = """
            SELECT id, task_id, payload, type
            FROM tasks
            WHERE status = '處理中' AND (
                depends_on IS NULL OR
                depends_on IN (SELECT task_id FROM tasks WHERE status = 'completed')
            )
            ORDER BY depends_on NULLS FIRST, created_at
            LIMIT 1
        """
        cursor.execute(sql)
        task = cursor.fetchone()

        if task:
            task_id_to_process = task["id"]
            log.info(f"🔒 找到並鎖定任務 ID: {task['task_id']} (資料庫 id: {task_id_to_process})")
            cursor.execute("UPDATE tasks SET status = 'processing' WHERE id = ?", (task_id_to_process,))
            return dict(task)
        else:
            log.debug("...佇列為空，無待處理任務。")
            return None
    except sqlite3.Error as e:
        log.error(f"❌ 獲取並鎖定任務時發生錯誤: {e}", exc_info=True)
        return None

def update_task_status(conn: sqlite3.Connection, task_id: str, status: str, result: str = None):
    sql = "UPDATE tasks SET status = ?, result = ? WHERE task_id = ?"
    try:
        conn.execute(sql, (status, result, task_id))
        log.info(f"✅ 任務 {task_id} 狀態已更新為: {status}")
    except sqlite3.Error as e:
        log.error(f"❌ 更新任務 {task_id} 狀態時出錯: {e}", exc_info=True)

def get_task_status(conn: sqlite3.Connection, task_id: str) -> dict | None:
    sql = "SELECT task_id, status, progress, type, payload, result, created_at, updated_at FROM tasks WHERE task_id = ?"
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (task_id,))
        task = cursor.fetchone()
        return dict(task) if task else None
    except sqlite3.Error as e:
        log.error(f"❌ 查詢任務 {task_id} 時發生錯誤: {e}", exc_info=True)
        return None

def find_dependent_task(conn: sqlite3.Connection, parent_task_id: str) -> str | None:
    sql = "SELECT task_id FROM tasks WHERE depends_on = ?"
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (parent_task_id,))
        task = cursor.fetchone()
        return task['task_id'] if task else None
    except sqlite3.Error as e:
        log.error(f"❌ 尋找依賴於 {parent_task_id} 的任務時出錯: {e}", exc_info=True)
        return None

def get_all_tasks(conn: sqlite3.Connection, task_type: str = None) -> list[dict]:
    params = []
    sql = "SELECT task_id, task_name, status, progress, type, payload, result, created_at, updated_at FROM tasks"
    if task_type:
        sql += " WHERE type = ?"
        params.append(task_type)
    sql += " ORDER BY created_at DESC"

    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        tasks = cursor.fetchall()
        return [dict(task) for task in tasks]
    except sqlite3.Error as e:
        log.error(f"❌ 獲取所有任務時發生錯誤: {e}", exc_info=True)
        return []

def add_system_log(conn: sqlite3.Connection, source: str, level: str, message: str) -> bool:
    sql = "INSERT INTO system_logs (source, level, message) VALUES (?, ?, ?)"
    try:
        conn.execute(sql, (source, level.upper(), message))
        return True
    except sqlite3.Error as e:
        print(f"CRITICAL: Failed to write system log to DB from source {source}. Error: {e}", file=sys.stderr)
        return False

def get_system_logs_by_filter(conn: sqlite3.Connection, levels: list[str] = None, sources: list[str] = None) -> list[dict]:
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

    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        logs = cursor.fetchall()
        return [dict(log) for log in logs]
    except sqlite3.Error as e:
        log.error(f"❌ 獲取系統日誌時發生錯誤: {e}", exc_info=True)
        return []

def clear_all_tasks(conn: sqlite3.Connection):
    sql = "DELETE FROM tasks"
    try:
        conn.execute(sql)
        log.info("✅ 已成功清空所有任務。")
        return True
    except sqlite3.Error as e:
        log.error(f"❌ 清理任務時發生錯誤: {e}", exc_info=True)
        return False

def get_all_app_states(conn: sqlite3.Connection) -> dict[str, str]:
    sql = "SELECT key, value FROM app_state"
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return {row['key']: row['value'] for row in rows}
    except sqlite3.Error as e:
        log.error(f"❌ 獲取所有 app_state 時發生錯誤: {e}", exc_info=True)
        return {}

if __name__ == "__main__":
    initialize_database()
