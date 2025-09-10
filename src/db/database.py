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
    # 檢查是否有測試專用的資料庫路徑環境變數
    db_path = os.environ.get("TEST_DB_PATH") or DB_FILE
    log.debug(f"正在連線到資料庫: {db_path}")
    try:
        # isolation_level=None 會開啟 autocommit 模式，但我們將手動管理交易
        conn = sqlite3.connect(db_path, timeout=10) # 增加 timeout
        conn.row_factory = sqlite3.Row # 將回傳結果設定為類似 dict 的物件
        # 啟用 WAL (Write-Ahead Logging) 模式以提高併發性
        if db_path != ":memory:": # WAL 模式不完全支援記憶體資料庫
            conn.execute("PRAGMA journal_mode=WAL")
        return conn
    except sqlite3.Error as e:
        log.error(f"資料庫連線失敗: {e}")
        return None

def initialize_database(conn: sqlite3.Connection = None):
    """
    初始化資料庫。如果資料表不存在，就建立它們。
    這個函式現在可以接受一個外部的資料庫連線物件，以便在測試中
    對記憶體資料庫進行操作。

    :param conn: 一個可選的 sqlite3.Connection 物件。如果未提供，
                 函式會自己建立一個連線到預設的資料庫檔案。
    """
    log.info(f"正在檢查並初始化資料庫...")

    # 標記是否需要在此函式結束時關閉連線
    close_conn_at_end = False
    if conn is None:
        # 在嘗試連線前，確保父目錄存在
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        conn = get_db_connection()
        if not conn:
            log.critical("無法建立資料庫連線，初始化失敗。")
            return
        close_conn_at_end = True
        log.info(f"使用預設資料庫檔案: {DB_FILE}")

    try:
        with conn: # 使用 with 陳述式來自動管理交易
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
            # Add columns if they don't exist (for migration)
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
                        pass # Column already exists, ignore
                    else:
                        raise
            # 建立索引以加速查詢
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON tasks (status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_id ON tasks (task_id)")

            # 新增一個觸發器來自動更新 updated_at 時間戳
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS update_tasks_updated_at
                AFTER UPDATE ON tasks
                FOR EACH ROW
                BEGIN
                    UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
                END;
            """)
            # 建立一個用於儲存系統日誌的資料表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    source TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT
                )
            """)
            # 為日誌表建立索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_source_level ON system_logs (source, level)")

            # --- JULES'S NEW FEATURE: 為 App State 建立資料表 ---
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
            # --- END ---

            # --- 新增 URL 提取功能資料表 ---
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
                extracted_image_paths TEXT
            )
            ''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON extracted_urls (url)")

            # --- 新增 AI 分析報告歷史紀錄資料表 ---
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
            # --- 結束 ---

            # --- 為 extracted_urls 進行簡易遷移，新增狀態相關欄位 ---
            url_migrations = {
                "status": "TEXT DEFAULT 'pending'",
                "status_message": "TEXT",
                "local_path": "TEXT",
                "file_hash": "TEXT",
                "extracted_image_paths": "TEXT"
            }
            for col, col_type in url_migrations.items():
                try:
                    cursor.execute(f"ALTER TABLE extracted_urls ADD COLUMN {col} {col_type}")
                    log.info(f"欄位 '{col}' 已成功新增至 'extracted_urls' 資料表。")
                except sqlite3.OperationalError as e:
                    # 如果欄位已存在，忽略此錯誤，繼續執行
                    if "duplicate column name" in str(e):
                        pass
                    else:
                        raise # 對於其他錯誤，則重新引發
            # --- 結束 ---

        log.info("✅ 資料庫初始化完成。`tasks`, `system_logs`, `app_state`, `extracted_urls` 資料表已存在。")
    except sqlite3.Error as e:
        log.error(f"初始化資料庫時發生錯誤: {e}")
    finally:
        # 只在函式內部自己建立連線時才關閉它
        if close_conn_at_end and conn:
            conn.close()


# --- JULES'S NEW FEATURE: App State 核心功能 ---

def set_app_state(key: str, value: str) -> bool:
    """
    儲存或更新一個鍵值對到 app_state 表中 (Upsert)。
    """
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
    """
    根據鍵從 app_state 表中獲取值。
    """
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


# --- 任務佇列核心功能 ---

def add_task(task_id: str, payload: str, task_type: str = 'transcribe', depends_on: str = None) -> bool:
    """
    新增一個新任務到佇列中。

    :param task_id: 唯一的任務 ID。
    :param payload: 任務的內容，通常是 JSON 字串。
    :param task_type: 任務類型 ('transcribe' 或 'download').
    :param depends_on: 此任務所依賴的另一個任務的 task_id。
    :return: 如果成功新增則回傳 True，否則回傳 False。
    """
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
    """
    以原子操作獲取一個待處理的任務，並將其狀態更新為 'processing'。
    這是確保多個 worker 不會同時處理同一個任務的關鍵。

    :return: 一個包含任務資訊的字典，如果沒有待處理任務則回傳 None。
    """
    conn = get_db_connection()
    if not conn: return None

    log.debug(f"DB:{DB_FILE} Worker 正在嘗試獲取任務...")
    try:
        # 使用 IMMEDIATE 交易來立即鎖定資料庫以進行寫入
        with conn:
            cursor = conn.cursor()
            # 1. 查詢一個可執行的待處理任務
            #    - 優先處理無依賴的任務 (例如下載任務)
            #    - 對於有依賴的任務，只有在其依賴的任務已完成時才選取
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
                # 2. 如果找到任務，立刻更新其狀態
                task_id_to_process = task["id"]
                log.info(f"🔒 找到並鎖定任務 ID: {task['task_id']} (資料庫 id: {task_id_to_process})")
                cursor.execute(
                    "UPDATE tasks SET status = 'processing' WHERE id = ?", (task_id_to_process,)
                )
                return dict(task)
            else:
                # 佇列中沒有待處理的任務
                log.debug("...佇列為空，無待處理任務。")
                return None
    except sqlite3.Error as e:
        log.error(f"❌ 獲取並鎖定任務時發生錯誤: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def update_task_progress(task_id: str, progress: int, partial_result: str):
    """
    更新任務的即時進度和部分結果。
    """
    # 將部分結果打包成與最終結果相同的 JSON 結構
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
    """
    更新一個任務的狀態和結果。

    :param task_id: 要更新的任務 ID。
    :param status: 新的狀態 ('已完成', 'failed')。
    :param result: 任務的結果或錯誤訊息。
    """
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
    """
    根據 task_id 查詢任務的狀態。

    :param task_id: 要查詢的任務 ID。
    :return: 包含任務狀態的字典，或如果找不到則回傳 None。
    """
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
    """
    尋找依賴於某個父任務的任務。

    :param parent_task_id: 依賴的父任務 ID。
    :return: 依賴任務的 task_id，如果找不到則回傳 None。
    """
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
    """
    檢查是否有任何正在處理中 (processing) 或待處理 (處理中) 的任務。
    這對於協調器的 IDLE 狀態檢測至關重要。

    :return: 如果有活動中任務則回傳 True，否則回傳 False。
    """
    sql = "SELECT 1 FROM tasks WHERE status IN ('處理中', 'processing') LIMIT 1"
    conn = get_db_connection()
    if not conn: return False # 如果無法連線，假設沒有活動任務以避免死鎖

    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        return cursor.fetchone() is not None
    except sqlite3.Error as e:
        log.error(f"❌ 檢查活動任務時發生錯誤: {e}", exc_info=True)
        return False # 發生錯誤時，同樣回傳 False
    finally:
        if conn:
            conn.close()


def get_all_tasks() -> list[dict]:
    """
    獲取資料庫中所有任務的列表，主要用於前端 UI 顯示。

    :return: 一個包含所有任務字典的列表。
    """
    sql = "SELECT task_id, status, progress, type, payload, result, created_at, updated_at FROM tasks ORDER BY created_at DESC"
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        tasks = cursor.fetchall()
        # 將 Row 物件轉換為標準字典列表
        return [dict(task) for task in tasks]
    except sqlite3.Error as e:
        log.error(f"❌ 獲取所有任務時發生錯誤: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def add_system_log(source: str, level: str, message: str) -> bool:
    """
    一個簡單的函式，用於從外部腳本（如 colab.py）直接寫入系統日誌。
    """
    sql = "INSERT INTO system_logs (source, level, message) VALUES (?, ?, ?)"
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn:
            conn.execute(sql, (source, level.upper(), message))
        return True
    except sqlite3.Error as e:
        # 在這種情況下，我們只在控制台打印錯誤，因為我們不能觸發日誌處理器
        print(f"CRITICAL: Failed to write system log to DB from source {source}. Error: {e}", file=sys.stderr)
        return False
    finally:
        if conn:
            conn.close()


def get_system_logs_by_filter(levels: list[str] = None, sources: list[str] = None) -> list[dict]:
    """
    根據等級和來源篩選，從資料庫獲取系統日誌。
    """
    conn = get_db_connection()
    if not conn: return []

    try:
        sql = "SELECT timestamp, source, level, message FROM system_logs"
        conditions = []
        params = []

        # 確保傳入的是列表
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
    """
    [僅供測試] 清空 `tasks` 資料表中的所有紀錄。
    """
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
    """
    從 app_state 表中獲取所有的鍵值對。
    """
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

def get_all_app_states() -> dict[str, str]:
    """
    從 app_state 表中獲取所有的鍵值對。
    """
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


if __name__ == "__main__":
    # 直接執行此檔案時，會進行初始化
    initialize_database()
