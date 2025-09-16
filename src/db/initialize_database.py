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

# --- SQL 定義: api_keys (V3) ---
API_KEYS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_name TEXT NOT NULL UNIQUE,
    key_hash TEXT NOT NULL UNIQUE,
    key_value TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active', -- active, cooldown, frozen
    last_used_at TIMESTAMP,
    cooldown_until TIMESTAMP,
    last_validated_at TIMESTAMP,
    is_valid BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    request_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    total_tokens_used INTEGER DEFAULT 0,
    cooldown_count INTEGER DEFAULT 0,
    frozen_until TIMESTAMP
);
"""

# --- SQL 定義: global_settings (V3) ---
GLOBAL_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS global_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# --- SQL 定義: key_health_status (V3) ---
KEY_HEALTH_STATUS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS key_health_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rpm_usage INTEGER,
    tpm_usage INTEGER,
    error_count_in_period INTEGER,
    FOREIGN KEY(key_id) REFERENCES api_keys(id) ON DELETE CASCADE
);
"""

def _add_column_if_not_exists(cursor: sqlite3.Cursor, table_name: str, column_name: str, column_definition: str):
    """輔助函式，檢查並新增欄位，確保舊版資料庫相容性。"""
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
    初始化資料庫 V3。
    """
    connection = None
    try:
        connection = sqlite3.connect(DB_PATH)
        # 啟用外鍵約束
        connection.execute("PRAGMA foreign_keys = ON;")
        cursor = connection.cursor()

        print("--- 正在處理 `api_keys` 表 (V3) ---")
        cursor.execute(API_KEYS_TABLE_SQL)
        _add_column_if_not_exists(cursor, 'api_keys', 'cooldown_count', 'INTEGER DEFAULT 0')
        _add_column_if_not_exists(cursor, 'api_keys', 'frozen_until', 'TIMESTAMP')

        print("\n--- 正在處理 `global_settings` 表 ---")
        cursor.execute(GLOBAL_SETTINGS_TABLE_SQL)
        # 填入預設的全域 RPM 值
        cursor.execute(
            "INSERT OR IGNORE INTO global_settings (key, value) VALUES (?, ?)",
            ("global_rpm", "15")
        )
        print("已設定/確認 `global_settings`。")


        print("\n--- 正在處理 `key_health_status` 表 ---")
        cursor.execute(KEY_HEALTH_STATUS_TABLE_SQL)
        print("已建立/確認 `key_health_status` 表。")

        # 移除舊的 model_quotas 表 (如果存在)
        print("\n--- 正在清理舊的資料表 ---")
        cursor.execute("DROP TABLE IF EXISTS model_quotas")
        print("舊的 `model_quotas` 表已成功移除 (如果存在)。")


        connection.commit()
        print(f"\n資料庫 V3 初始化/更新成功。資料庫檔案位於: {DB_PATH}")

    except sqlite3.Error as e:
        print(f"資料庫操作時發生錯誤: {e}", file=sys.stderr)
        if connection:
            connection.rollback()
    finally:
        if connection:
            connection.close()

if __name__ == "__main__":
    print("--- 正在執行資料庫初始化/更新腳本 (V3) ---")
    initialize()
    print("--- 腳本執行完畢 ---")
