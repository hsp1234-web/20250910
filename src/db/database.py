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
                extracted_image_paths TEXT,
                extracted_text TEXT
            )
            ''')
            # 方案 A: 建立唯一索引以優化 URL 去重效能
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uidx_url ON extracted_urls (url)")
            # Jules @ 2025-09-17: 為狀態查詢優化新增索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_urls_status ON extracted_urls (status)")

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

            # --- 為 API 金鑰管理建立資料表 (V4 重構) ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_name TEXT NOT NULL UNIQUE,
                    key_hash TEXT NOT NULL UNIQUE,
                    key_value TEXT NOT NULL,
                    is_valid INTEGER NOT NULL DEFAULT 0,
                    last_validated_at TEXT,
                    total_tokens_used INTEGER DEFAULT 0,
                    request_count INTEGER DEFAULT 0,
                    last_used_at TEXT,
                    status TEXT DEFAULT 'active'
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_key_hash ON api_keys (key_hash)")

            # --- JULES'S FIX (2025-09-30): 為 api_keys 表格新增 key_type 欄位 ---
            # 解決因資料庫綱要未同步更新，導致查詢時缺少欄位的錯誤
            try:
                cursor.execute("ALTER TABLE api_keys ADD COLUMN key_type TEXT NOT NULL DEFAULT 'gemini'")
                log.info("欄位 'key_type' 已成功新增至 'api_keys' 資料表。")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    pass # 欄位已存在，是正常情況
                else:
                    raise # 其他錯誤則需拋出
            # --- 結束 ---

            # --- 結束 ---

            # --- 為兩階段 AI 分析流程建立新資料表 ---
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                stage1_status VARCHAR(20) DEFAULT 'pending',
                stage1_model TEXT,
                stage1_json_path TEXT,
                stage1_error_log TEXT,
                stage1_token_usage INTEGER,
                stage2_status VARCHAR(20) DEFAULT 'pending',
                stage2_model_used TEXT,
                stage2_report_path TEXT,
                stage2_error_log TEXT,
                stage2_token_usage INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES extracted_urls (id)
            )
            ''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_analysis_file_id ON analysis_tasks (file_id)")
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS update_analysis_tasks_updated_at
                AFTER UPDATE ON analysis_tasks
                FOR EACH ROW
                BEGIN
                    UPDATE analysis_tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
                END;
            """)
            # --- 結束 ---

            # --- 為 extracted_urls 進行簡易遷移，新增狀態相關欄位 ---
            url_migrations = {
                "author": "TEXT", # 新增作者欄位
                "message_date": "TEXT", # 訊息本身的日期
                "message_time": "TEXT", # 訊息本身的時間
                "title": "TEXT", # (Jules @ 2025-09-17) 新增標題欄位
                "status": "TEXT DEFAULT 'pending'",
                "status_message": "TEXT",
                "local_path": "TEXT",
                "file_hash": "TEXT",
                "extracted_image_paths": "TEXT",
                "extracted_text": "TEXT",
                "retry_count": "INTEGER DEFAULT 0", # 為重試機制新增
                "last_error_details": "TEXT" # 為重試機制新增
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

            # --- 為 reports 表格新增 structured_data 欄位 ---
            try:
                cursor.execute("ALTER TABLE reports ADD COLUMN structured_data TEXT")
                log.info("欄位 'structured_data' 已成功新增至 'reports' 資料表。")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    pass
                else:
                    raise
            # --- 結束 ---

            # --- 為 analysis_tasks 表格新增 file_content_for_analysis 欄位 (2025-09-13) ---
            try:
                cursor.execute("ALTER TABLE analysis_tasks ADD COLUMN file_content_for_analysis TEXT")
                log.info("欄位 'file_content_for_analysis' 已成功新增至 'analysis_tasks' 資料表。")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    pass # 欄位已存在，是正常情況
                else:
                    raise # 其他錯誤則需拋出
            # --- 結束 ---

            # --- 為 analysis_tasks 表格新增 token usage 欄位 (2025-09-13) ---
            token_migrations = {
                "stage1_token_usage": "INTEGER",
                "stage2_token_usage": "INTEGER"
            }
            for col, col_type in token_migrations.items():
                try:
                    cursor.execute(f"ALTER TABLE analysis_tasks ADD COLUMN {col} {col_type}")
                    log.info(f"欄位 '{col}' 已成功新增至 'analysis_tasks' 資料表。")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e):
                        pass
                    else:
                        raise
            # --- 結束 ---

            # --- 為 analysis_tasks 新增績效分析相關欄位 (2025-09-15) ---
            performance_migrations = {
                "performance_status": "VARCHAR(20) DEFAULT 'pending'",
                "performance_error_log": "TEXT"
            }
            for col, col_type in performance_migrations.items():
                try:
                    cursor.execute(f"ALTER TABLE analysis_tasks ADD COLUMN {col} {col_type}")
                    log.info(f"欄位 '{col}' 已成功新增至 'analysis_tasks' 資料表。")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e):
                        pass
                    else:
                        raise
            # --- 結束 ---

            # --- 為 analysis_tasks 新增 AI 推斷日期欄位 (2025-09-15) ---
            date_inference_migrations = {
                "inferred_publish_date": "TEXT",
                "date_inference_status": "VARCHAR(20) DEFAULT 'pending'"
            }
            for col, col_type in date_inference_migrations.items():
                try:
                    cursor.execute(f"ALTER TABLE analysis_tasks ADD COLUMN {col} {col_type}")
                    log.info(f"欄位 '{col}' 已成功新增至 'analysis_tasks' 資料表。")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e):
                        pass
                    else:
                        raise
            # --- 結束 ---

            # --- 為 analysis_tasks 新增更多分析欄位 (2025-09-15) ---
            more_analysis_migrations = {
                "date_inference_model": "TEXT",
                "date_inference_token_usage": "INTEGER",
                "performance_model": "TEXT",
                "performance_token_usage": "INTEGER"
            }
            for col, col_type in more_analysis_migrations.items():
                try:
                    cursor.execute(f"ALTER TABLE analysis_tasks ADD COLUMN {col} {col_type}")
                    log.info(f"欄位 '{col}' 已成功新增至 'analysis_tasks' 資料表。")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e):
                        pass
                    else:
                        raise
            # --- 結束 ---

            # --- 為 analysis_tasks 新增重點摘要相關欄位 (2025-09-21) ---
            summary_migrations = {
                "summary_status": "VARCHAR(20) DEFAULT 'pending'",
                "summary_model": "TEXT",
                "summary_token_usage": "INTEGER",
                "summary_error_log": "TEXT",
                "summary_content": "TEXT"
            }
            for col, col_type in summary_migrations.items():
                try:
                    cursor.execute(f"ALTER TABLE analysis_tasks ADD COLUMN {col} {col_type}")
                    log.info(f"欄位 '{col}' 已成功新增至 'analysis_tasks' 資料表。")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e):
                        pass # 欄位已存在，是正常情況
                    else:
                        raise # 其他錯誤則需拋出
            # --- 結束 ---

        log.info("✅ 資料庫初始化完成。`tasks`, `system_logs`, `app_state`, `extracted_urls`, `reports`, `analysis_tasks` 資料表已存在。")
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


# --- 新增：AI 分析任務 (Analysis Tasks) 專用函式 ---

def create_or_get_analysis_task(file_id: int, filename: str) -> dict | None:
    """
    為指定的 file_id 建立或取得一個分析任務。
    如果任務已存在，則直接回傳該任務。如果不存在，則建立一個新的。
    :param file_id: 來源檔案的 ID (來自 extracted_urls)。
    :param filename: 檔案名稱。
    :return: 包含任務資訊的字典，或失敗時回傳 None。
    """
    conn = get_db_connection()
    if not conn: return None

    try:
        with conn:
            cursor = conn.cursor()
            # 檢查是否已存在
            cursor.execute("SELECT * FROM analysis_tasks WHERE file_id = ?", (file_id,))
            existing_task = cursor.fetchone()

            if existing_task:
                log.info(f"分析任務 for file_id {file_id} 已存在，直接回傳。")
                return dict(existing_task)

            # 不存在，則建立新的
            sql = "INSERT INTO analysis_tasks (file_id, filename) VALUES (?, ?)"
            cursor.execute(sql, (file_id, filename))
            new_task_id = cursor.lastrowid
            log.info(f"✅ 已為 file_id {file_id} 建立新的分析任務，ID: {new_task_id}。")

            # 取得並回傳剛建立的任務
            cursor.execute("SELECT * FROM analysis_tasks WHERE id = ?", (new_task_id,))
            new_task = cursor.fetchone()
            return dict(new_task) if new_task else None

    except sqlite3.Error as e:
        log.error(f"❌ 建立或取得分析任務 for file_id {file_id} 時發生錯誤: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def update_analysis_task(task_id: int, updates: dict) -> bool:
    """
    通用更新函式，用來更新 analysis_tasks 表中的特定欄位。
    :param task_id: 要更新的任務 ID。
    :param updates: 一個字典，key 是欄位名，value 是要更新的值。
    :return: 成功則回傳 True，否則 False。
    """
    if not updates:
        log.warning("呼叫 update_analysis_task 時沒有提供任何更新內容。")
        return False

    conn = get_db_connection()
    if not conn: return False

    set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
    params = list(updates.values())
    params.append(task_id)

    sql = f"UPDATE analysis_tasks SET {set_clause} WHERE id = ?"

    try:
        with conn:
            conn.execute(sql, params)
        log.info(f"✅ 分析任務 {task_id} 已更新: {updates}")
        return True
    except sqlite3.Error as e:
        log.error(f"❌ 更新分析任務 {task_id} 時出錯: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()

def get_all_analysis_tasks() -> list[dict]:
    """
    獲取所有 AI 分析任務的列表，並連帶查詢關聯的 file_hash 和 author。
    :return: 一個包含所有分析任務字典的列表。
    """
    # 2025-09-13: Jules 修改了 SQL 查詢，以 JOIN extracted_urls 來獲取 file_hash 和 author
    sql = """
        SELECT
            at.*,
            eu.file_hash,
            eu.author
        FROM
            analysis_tasks at
        LEFT JOIN
            extracted_urls eu ON at.file_id = eu.id
        ORDER BY
            at.created_at DESC
    """
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        tasks = cursor.fetchall()
        return [dict(task) for task in tasks]
    except sqlite3.Error as e:
        log.error(f"❌ 獲取所有分析任務時發生錯誤: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()

def get_analysis_task(task_id: int) -> dict | None:
    """
    根據主鍵 ID 獲取單一分析任務。
    :param task_id: 任務的主鍵 ID。
    :return: 包含任務資訊的字典，或如果找不到則回傳 None。
    """
    sql = "SELECT * FROM analysis_tasks WHERE id = ?"
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (task_id,))
        task = cursor.fetchone()
        return dict(task) if task else None
    except sqlite3.Error as e:
        log.error(f"❌ 查詢分析任務 {task_id} 時發生錯誤: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

# --- 結束：AI 分析任務專用函式 ---


# --- 新增：extracted_urls 專用函式 (2025-09-13) ---

def get_url_by_id(url_id: int) -> dict | None:
    """根據主鍵 ID 獲取單一 URL 紀錄。"""
    sql = "SELECT * FROM extracted_urls WHERE id = ?"
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (url_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        log.error(f"❌ 查詢 URL ID {url_id} 時發生錯誤: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def update_url(url_id: int, updates: dict) -> bool:
    """通用更新函式，用來更新 extracted_urls 表中的特定欄位。"""
    if not updates:
        log.warning("呼叫 update_url 時沒有提供任何更新內容。")
        return False

    conn = get_db_connection()
    if not conn: return False

    set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
    params = list(updates.values())
    params.append(url_id)

    sql = f"UPDATE extracted_urls SET {set_clause} WHERE id = ?"

    try:
        with conn:
            conn.execute(sql, params)
        log.info(f"✅ URL 紀錄 {url_id} 已更新: {updates}")
        return True
    except sqlite3.Error as e:
        log.error(f"❌ 更新 URL 紀錄 {url_id} 時出錯: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def get_urls_by_statuses(statuses: list[str]) -> list[dict]:
    """根據狀態列表獲取所有相關的 URL 紀錄。"""
    if not statuses:
        return []

    conn = get_db_connection()
    if not conn: return []

    try:
        # 為 IN 子句建立一個佔位符字串
        placeholders = ','.join(['?'] * len(statuses))
        # 2025-09-18 V4 優化：查詢所有欄位以滿足不同頁面的需求
        # 2025-09-17 Jules 修正：明確指定欄位，排除大型的 source_text 欄位以優化效能
        sql = f"""
            SELECT
                id, url, created_at, status, status_message, local_path,
                file_hash, extracted_image_paths, extracted_text, author,
                message_date, message_time, title, retry_count, last_error_details
            FROM
                extracted_urls
            WHERE
                status IN ({placeholders})
            ORDER BY
                created_at DESC
        """

        cursor = conn.cursor()
        cursor.execute(sql, statuses)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        log.error(f"❌ 根據 statuses {statuses} 查詢 URLs 時發生錯誤: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


# --- 結束 ---


def get_performance_dashboard_data() -> list[dict]:
    """
    (V4 優化新增) 獲取績效儀表板所需的所有數據。
    使用 JOIN 查詢以避免 N+1 問題。
    """
    sql = """
        SELECT
            at.id,
            at.stage1_json_path,
            eu.author,
            eu.message_date
        FROM
            analysis_tasks at
        JOIN
            extracted_urls eu ON at.file_id = eu.id
        WHERE
            at.performance_status = 'completed' AND at.stage1_json_path IS NOT NULL
        ORDER BY
            at.created_at DESC
    """
    conn = get_db_connection()
    if not conn: return []

    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        log.error(f"獲取儀表板數據時發生錯誤: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


# --- 新增：檔案總覽頁面專用函式 (2025-09-13) ---

def get_urls_by_hash(file_hash: str) -> list[dict]:
    """根據檔案雜湊值獲取所有相關的 URL 紀錄。"""
    sql = "SELECT * FROM extracted_urls WHERE file_hash = ? ORDER BY created_at ASC"
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (file_hash,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        log.error(f"❌ 根據 hash {file_hash} 查詢 URLs 時發生錯誤: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()

def get_analysis_task_by_file_id(file_id: int) -> dict | None:
    """根據 file_id 獲取單一分析任務。"""
    sql = "SELECT * FROM analysis_tasks WHERE file_id = ?"
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (file_id,))
        task = cursor.fetchone()
        return dict(task) if task else None
    except sqlite3.Error as e:
        log.error(f"❌ 根據 file_id {file_id} 查詢分析任務時發生錯誤: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def add_new_urls(parsed_data: list[dict], source_text: str) -> int:
    """
    (V38 效能優化) 將解析後的結構化資料儲存到資料庫。
    使用 INSERT OR IGNORE 和 UNIQUE 索引來高效處理重複資料。
    返回新增的紀錄數量。
    """
    if not parsed_data:
        log.info("沒有要儲存的資料，跳過資料庫操作。")
        return 0

    conn = get_db_connection()
    if not conn:
        log.error("無法建立資料庫連線，資料儲存失敗。")
        return 0

    try:
        # 延遲匯入以避免循環依賴
        from core.time_utils import get_current_taipei_time_iso
        created_at_iso = get_current_taipei_time_iso()

        data_to_insert = [
            (item['url'], item['author'], item['date'], item['time'], item.get('title', '無標題'), source_text, created_at_iso)
            for item in parsed_data
        ]

        with conn:
            cursor = conn.cursor()

            # 記錄操作前的總變更數
            before_changes = conn.total_changes

            # 使用 INSERT OR IGNORE，如果 URL 已存在，資料庫會自動忽略該筆，不會報錯
            cursor.executemany(
                "INSERT OR IGNORE INTO extracted_urls (url, author, message_date, message_time, title, source_text, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
                data_to_insert
            )

            # 計算實際新增的筆數
            after_changes = conn.total_changes
            count = after_changes - before_changes

        if count > 0:
            log.info(f"✅ 成功新增 {count} 筆資料至資料庫 (忽略了 {len(data_to_insert) - count} 筆重複資料)。")
        else:
            log.info("所有解析出的網址都已存在於資料庫中，無需新增。")

        return count
    except sqlite3.Error as e:
        log.error(f"儲存解析資料到資料庫時發生錯誤: {e}", exc_info=True)
        return 0
    finally:
        if conn:
            conn.close()


def get_filtered_urls(start_date: str = None, end_date: str = None) -> list[dict]:
    """
    (V4 優化新增) 根據日期範圍獲取 URL 紀錄。
    (Jules @ 2025-09-17) 修改以回傳卡片所需的所有欄位。
    """
    # Jules @ 2025-09-17: 新增 title, message_time, 和 status 欄位以支援卡片模式
    query = "SELECT id, url, author, message_date, message_time, title, status FROM extracted_urls"
    filters = []
    params = []

    if start_date:
        filters.append("message_date >= ?")
        params.append(start_date)
    if end_date:
        filters.append("message_date <= ?")
        params.append(end_date)

    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY created_at DESC"

    conn = get_db_connection()
    if not conn: return []

    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        # Jules @ 2025-09-17: 直接回傳完整的字典，讓前端處理
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        log.error(f"查詢總覽資料時發生錯誤: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()

# --- 結束 ---


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
