# scripts/migrate_keys_to_db.py
import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# --- 路徑設定 ---
# 解決模組引用問題
ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

# --- 檔案路徑 ---
OLD_KEYS_JSON_PATH = SRC_DIR / "db" / "secrets" / "keys.json"
DB_PATH = SRC_DIR / "db" / "database.sqlite3"

def migrate_keys():
    """
    將舊的 keys.json 檔案中的金鑰遷移到新的 SQLite 資料庫。
    此腳本可安全地重複執行。
    """
    print("--- 開始金鑰資料遷移 ---")

    # 1. 檢查並讀取舊的 JSON 檔案
    if not OLD_KEYS_JSON_PATH.exists():
        print(f"找不到舊的金鑰檔案: {OLD_KEYS_JSON_PATH}")
        print("無需遷移。")
        return

    try:
        with open(OLD_KEYS_JSON_PATH, 'r', encoding='utf-8') as f:
            old_keys = json.load(f)
        if not isinstance(old_keys, list):
            raise TypeError("金鑰檔案格式不正確，應為一個列表。")
        print(f"從 {OLD_KEYS_JSON_PATH} 中找到 {len(old_keys)} 筆金鑰資料。")
    except (json.JSONDecodeError, TypeError) as e:
        print(f"讀取或解析舊金鑰檔案時發生錯誤: {e}", file=sys.stderr)
        return

    # 2. 連接到資料庫
    if not DB_PATH.exists():
        print(f"錯誤：找不到資料庫檔案 {DB_PATH}。", file=sys.stderr)
        print("請先執行 `src/db/initialize_database.py` 來建立資料庫。", file=sys.stderr)
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        migrated_count = 0
        skipped_count = 0

        # 3. 遍歷舊金鑰並插入新資料庫
        for i, key_data in enumerate(old_keys):
            key_hash = key_data.get("key_hash")
            key_value = key_data.get("key_value")

            if not key_hash or not key_value:
                print(f"警告：第 {i+1} 筆資料缺少 'key_hash' 或 'key_value'，已跳過。")
                continue

            # 檢查金鑰是否已存在於資料庫中
            cursor.execute("SELECT id FROM api_keys WHERE key_hash = ?", (key_hash,))
            if cursor.fetchone():
                # print(f"金鑰 {key_hash[:8]}... 已存在於資料庫中，已跳過。")
                skipped_count += 1
                continue

            # 準備要插入的資料
            params = {
                "key_name": key_data.get("name", f"Migrated-Key-{i+1}"),
                "key_hash": key_hash,
                "key_value": key_value,
                "status": "active",
                "last_validated_at": key_data.get("last_validated"), # 欄位名映射
                "is_valid": bool(key_data.get("is_valid", False)),
                "created_at": datetime.now().isoformat()
            }

            # 執行插入
            query = """
                INSERT INTO api_keys (key_name, key_hash, key_value, status, last_validated_at, is_valid, created_at)
                VALUES (:key_name, :key_hash, :key_value, :status, :last_validated_at, :is_valid, :created_at)
            """
            cursor.execute(query, params)
            migrated_count += 1

        conn.commit()

        print("\n--- 遷移結果 ---")
        print(f"成功遷移: {migrated_count} 筆新金鑰。")
        print(f"因已存在而跳過: {skipped_count} 筆金鑰。")
        print("------------------")

    except sqlite3.Error as e:
        print(f"資料庫操作時發生錯誤: {e}", file=sys.stderr)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    migrate_keys()
