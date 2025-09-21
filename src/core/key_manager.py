# src/core/key_manager.py
import hashlib
import os
import sqlite3
import sys
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 路徑修正與設定 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))
ROOT_DIR = SRC_DIR.parent
DB_PATH = SRC_DIR / "db" / "database.sqlite3"

# --- 核心資料庫輔助函式 ---

def _execute_query(query: str, params: Tuple = (), fetch: Optional[str] = None) -> Any:
    """
    執行資料庫查詢的統一輔助函式。
    :param query: SQL 查詢語句。
    :param params: 要傳遞給查詢的參數元組。
    :param fetch: 'one' 表示獲取單筆結果，'all' 表示獲取所有結果，None 表示不獲取結果（用於 INSERT, UPDATE, DELETE）。
    :return: 根據 fetch 參數返回查詢結果。
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"資料庫檔案不存在於: {DB_PATH}。請先執行 initialize_database.py 腳本。")

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        # 設定 Row Factory，讓回傳結果為字典形式，更易於操作
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)

        if fetch == 'one':
            result = cursor.fetchone()
            return result
        elif fetch == 'all':
            result = cursor.fetchall()
            return result
        else:
            conn.commit()
            # 對於寫入操作，回傳影響的行數
            return cursor.rowcount
    except sqlite3.Error as e:
        print(f"資料庫錯誤: {e}\n查詢: {query}\n參數: {params}", file=sys.stderr)
        # 在生產環境中，這裡應該使用更強大的日誌記錄
        raise  # 重新拋出例外，讓上層處理
    finally:
        if conn:
            conn.close()

# --- 內部輔助函式 ---

def _hash_key(key: str) -> str:
    """對金鑰進行 SHA256 雜湊，只取前 16 位以便於使用。"""
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def _validate_single_key(api_key: str) -> bool:
    """
    呼叫 gemini_processor.py 工具來驗證單一金鑰的有效性。
    此版本已移除內部重試迴圈，僅執行單次驗證。
    """
    tool_script_path = ROOT_DIR / "src" / "tools" / "gemini_processor.py"
    cmd = [sys.executable, str(tool_script_path), "--command=validate_key"]
    env = os.environ.copy()
    env["GOOGLE_API_KEY"] = api_key

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding='utf-8',
            env=env, check=False, timeout=20  # 縮短單次超時
        )
        if result.returncode == 0:
            return True
        else:
            # 在背景執行緒中，只記錄簡短的錯誤訊息
            error_msg = (result.stderr or result.stdout or "未知錯誤").strip()
            # print(f"金鑰驗證失敗: {error_msg}", file=sys.stderr)
            return False
    except subprocess.TimeoutExpired:
        # print(f"金鑰驗證超時。", file=sys.stderr)
        return False
    except Exception:
        # print(f"金鑰驗證發生例外: {e}", file=sys.stderr)
        return False

# --- 公開 API (介面維持不變) ---

def get_all_keys() -> List[Dict[str, Any]]:
    """獲取所有金鑰的狀態，但不包含原始金鑰值。"""
    query = "SELECT key_name, key_hash, is_valid, last_validated_at, total_tokens_used FROM api_keys ORDER BY id"
    rows = _execute_query(query, fetch='all')
    # 將 sqlite3.Row 物件轉換為標準字典，並符合舊版函式的輸出格式
    return [
        {
            "name": row["key_name"],
            "key_hash": row["key_hash"],
            "is_valid": bool(row["is_valid"]),
            "last_validated": row["last_validated_at"],
            "total_tokens_used": row["total_tokens_used"]
        } for row in rows
    ]

def add_key(key_value: str, key_name: Optional[str] = None, validate: bool = True) -> Dict[str, Any]:
    """新增一個金鑰到資料庫。"""
    if not key_value or not key_value.strip():
        raise ValueError("API 金鑰不可為空。")

    key_hash = _hash_key(key_value)

    # 檢查金鑰是否已存在
    if _execute_query("SELECT id FROM api_keys WHERE key_hash = ?", (key_hash,), fetch='one'):
        raise ValueError("此 API 金鑰已存在。")

    is_valid = False
    validation_time = None
    if validate:
        is_valid = _validate_single_key(key_value)
        validation_time = datetime.now().isoformat()

    final_key_name = key_name or f"Key-{int(time.time())}" # 使用時間戳確保唯一性

    query = """
        INSERT INTO api_keys (key_name, key_hash, key_value, is_valid, last_validated_at, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    params = (final_key_name, key_hash, key_value, is_valid, validation_time, 'active')
    _execute_query(query, params)

    # 回傳與舊版函式相同的格式
    return {"name": final_key_name, "key_hash": key_hash, "is_valid": is_valid}

def delete_key(key_hash: str) -> bool:
    """根據雜湊值從資料庫中刪除一個金鑰。"""
    affected_rows = _execute_query("DELETE FROM api_keys WHERE key_hash = ?", (key_hash,))
    return affected_rows > 0

def clear_all_keys() -> int:
    """
    (Jules @ 2025-09-21) 從資料庫中刪除所有 API 金鑰，用於啟動時的環境清理。
    """
    # SQLite 特有的語法，用於重設自動遞增的主鍵
    _execute_query("DELETE FROM sqlite_sequence WHERE name='api_keys'")
    affected_rows = _execute_query("DELETE FROM api_keys")
    return affected_rows

def validate_all_keys() -> List[Dict[str, Any]]:
    """
    並行重新驗證所有已儲存的金鑰，以提升效率。
    """
    keys_to_validate = _execute_query("SELECT id, key_value FROM api_keys", fetch='all')
    if not keys_to_validate:
        return []

    # 使用執行緒池並行處理所有金鑰的驗證
    with ThreadPoolExecutor(max_workers=10) as executor:
        # 建立 future 到 key_id 的映射
        future_to_key_id = {executor.submit(_validate_single_key, key["key_value"]): key["id"] for key in keys_to_validate}

        for future in as_completed(future_to_key_id):
            key_id = future_to_key_id[future]
            try:
                is_valid = future.result()
                validation_time = datetime.now().isoformat()
                query = "UPDATE api_keys SET is_valid = ?, last_validated_at = ? WHERE id = ?"
                _execute_query(query, (is_valid, validation_time, key_id))
            except Exception as exc:
                print(f"處理金鑰 ID {key_id} 的驗證時產生錯誤: {exc}", file=sys.stderr)

    return get_all_keys()

def get_valid_key() -> Optional[str]:
    """
    從池中獲取一個有效的金鑰。
    策略：優先選取最久未被使用的活躍金鑰。
    """
    query = """
        SELECT id, key_value FROM api_keys
        WHERE status = 'active' AND is_valid = 1
        ORDER BY last_used_at ASC NULLS FIRST
        LIMIT 1
    """
    key_row = _execute_query(query, fetch='one')

    if key_row:
        # 標記此金鑰為已使用
        update_query = "UPDATE api_keys SET last_used_at = ? WHERE id = ?"
        _execute_query(update_query, (datetime.now().isoformat(), key_row["id"]))
        return key_row["key_value"]

    return None

def get_all_valid_keys_for_manager() -> List[Dict[str, str]]:
    """獲取所有有效的金鑰，格式為 GeminiManager 所需的列表。"""
    query = "SELECT key_name, key_value FROM api_keys WHERE is_valid = 1 AND status = 'active'"
    rows = _execute_query(query, fetch='all')
    return [{"name": row["key_name"], "value": row["key_value"]} for row in rows]

def test_key(api_key: str) -> bool:
    """公開的函式，用於測試單一 API 金鑰的有效性，而不將其儲存。"""
    if not api_key:
        return False
    return _validate_single_key(api_key)

def add_keys_from_environment(count: int) -> Dict[str, Any]:
    """
    從環境變數中讀取 API 金鑰並將其新增到金鑰池。
    此函式依賴於 add_key，其介面未變，故此處邏輯不需大改。
    """
    if not isinstance(count, int) or count < 0:
        raise ValueError("金鑰數量必須是一個非負整數。")

    base_key_name = "GOOGLE_API_KEY"
    target_key_names = [base_key_name]
    if count > 0:
        target_key_names.extend([f"{base_key_name}_{i}" for i in range(1, count + 1)])

    summary = {
        "total_attempted": len(target_key_names), "successfully_added": 0,
        "already_existed": 0, "not_found": 0, "invalid_keys": 0, "details": []
    }

    for key_name in target_key_names:
        key_value = os.environ.get(key_name)
        if not key_value:
            summary["not_found"] += 1
            summary["details"].append({"name": key_name, "status": "未在環境變數中找到"})
            continue
        try:
            # 呼叫已重構的 add_key 函式
            result = add_key(key_value, key_name)
            if result.get("is_valid"):
                summary["successfully_added"] += 1
                summary["details"].append({"name": key_name, "status": "成功新增並驗證"})
            else:
                summary["invalid_keys"] += 1
                summary["details"].append({"name": key_name, "status": "新增但驗證失敗"})
        except ValueError:
            summary["already_existed"] += 1
            summary["details"].append({"name": key_name, "status": "已存在，跳過"})
        except Exception as e:
            summary["details"].append({"name": key_name, "status": f"發生未預期錯誤: {e}"})
    return summary

def record_token_usage(key_name: str, tokens_used: int):
    """
    記錄指定金鑰的 token 使用量。
    """
    if not key_name or tokens_used is None or tokens_used < 0:
        return

    query = """
        UPDATE api_keys
        SET
            total_tokens_used = total_tokens_used + ?,
            request_count = request_count + 1
        WHERE key_name = ?
    """
    try:
        _execute_query(query, (tokens_used, key_name))
    except Exception as e:
        # 在這裡，我們選擇不讓 token 記錄的失敗影響到主流程
        print(f"警告：記錄金鑰 '{key_name}' 的 token 使用量時發生錯誤: {e}", file=sys.stderr)
