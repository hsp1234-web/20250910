# src/core/key_manager.py
import hashlib
import os
import sqlite3
import sys
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple, Callable
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import fredapi

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
    (Gemini) 呼叫 gemini_processor.py 工具來驗證單一 Gemini 金鑰的有效性。
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
            return False
    except (subprocess.TimeoutExpired, Exception):
        return False

def _validate_fred_key(api_key: str) -> bool:
    """
    (FRED) 驗證 FRED API 金鑰的有效性。
    透過一個簡單的 API 請求來測試金鑰是否能成功驗證。
    """
    if not api_key:
        return False
    try:
        fred = fredapi.Fred(api_key=api_key)
        # 嘗試獲取一個常見但數據量小的序列的資訊，以測試金鑰
        fred.get_series_info('GNP')
        return True
    except Exception:
        # 任何例外都表示金鑰無效或 API 無法訪問
        return False

# --- 公開 API (介面維持不變) ---

def get_all_keys() -> List[Dict[str, Any]]:
    """獲取所有金鑰的狀態，但不包含原始金鑰值。"""
    query = "SELECT key_name, key_hash, key_type, is_valid, last_validated_at, total_tokens_used FROM api_keys ORDER BY id"
    rows = _execute_query(query, fetch='all')
    # 將 sqlite3.Row 物件轉換為標準字典
    return [
        {
            "name": row["key_name"],
            "key_hash": row["key_hash"],
            "key_type": row["key_type"],
            "is_valid": bool(row["is_valid"]),
            "last_validated": row["last_validated_at"],
            "total_tokens_used": row["total_tokens_used"]
        } for row in rows
    ]

def add_key(key_value: str, key_name: Optional[str] = None, key_type: str = 'gemini', validate: bool = True) -> Dict[str, Any]:
    """新增一個金鑰到資料庫，並可選擇是否進行驗證。"""
    if not key_value or not key_value.strip():
        raise ValueError("API 金鑰不可為空。")
    if key_type not in ['gemini', 'fred']:
        raise ValueError("無效的金鑰類型。必須是 'gemini' 或 'fred'。")

    key_hash = _hash_key(key_value)

    if _execute_query("SELECT id FROM api_keys WHERE key_hash = ?", (key_hash,), fetch='one'):
        raise ValueError("此 API 金鑰已存在。")

    is_valid = False
    validation_time = None

    if validate:
        validation_time = datetime.now().isoformat()
        if key_type == 'gemini':
            is_valid = _validate_single_key(key_value)
        elif key_type == 'fred':
            is_valid = _validate_fred_key(key_value)
        # 未來可在此處擴充其他金鑰類型的驗證

    final_key_name = key_name or f"{key_type.capitalize()}-Key-{int(time.time())}"

    query = """
        INSERT INTO api_keys (key_name, key_hash, key_value, key_type, is_valid, last_validated_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    params = (final_key_name, key_hash, key_value, key_type, is_valid, validation_time, 'active')
    _execute_query(query, params)

    return {"name": final_key_name, "key_hash": key_hash, "key_type": key_type, "is_valid": is_valid}

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
    並行重新驗證所有已儲存的金鑰，根據其類型選擇合適的驗證器。
    """
    keys_to_validate = _execute_query("SELECT id, key_value, key_type FROM api_keys", fetch='all')
    if not keys_to_validate:
        return []

    # 建立一個金鑰類型到其對應驗證函式的映射
    validator_map: Dict[str, Callable[[str], bool]] = {
        'gemini': _validate_single_key,
        'fred': _validate_fred_key
    }

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_key_id = {}
        for key in keys_to_validate:
            validator = validator_map.get(key["key_type"])
            if validator:
                # 如果找到對應的驗證器，則提交任務
                future = executor.submit(validator, key["key_value"])
                future_to_key_id[future] = key["id"]
            else:
                # 如果沒有驗證器，可以選擇跳過或標記為未驗證
                print(f"警告：金鑰 ID {key['id']} 的類型 '{key['key_type']}' 沒有對應的驗證器，已跳過。", file=sys.stderr)

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

def test_key(api_key: str, key_type: str = 'gemini') -> bool:
    """
    公開的函式，用於測試單一 API 金鑰的有效性，而不將其儲存。
    :param api_key: 要測試的金鑰值。
    :param key_type: 金鑰的類型 ('gemini', 'fred', 等)。
    """
    if not api_key:
        return False

    if key_type == 'gemini':
        return _validate_single_key(api_key)
    elif key_type == 'fred':
        return _validate_fred_key(api_key)

    # 對於未知的類型，可以預設返回 False 或拋出錯誤
    return False


# --- JULES (2025-09-30): 新增函式以自動註冊 FRED 金鑰 ---
def sync_fred_key_from_env():
    """
    自動從環境變數同步 FRED API 金鑰。

    此函式會檢查 `FRED_API_KEY` 環境變數。如果該金鑰存在但尚未存入資料庫，
    它會自動將其新增，確保系統啟動時 FRED 金鑰的可用性。
    """
    # 注意：此處使用 print 是為了與協調器的日誌輸出保持一致，因其會捕獲 stdout。
    # 在理想情況下，應傳入一個日誌記錄器實例。
    print("INFO: [金鑰管理器] 正在檢查並同步環境中的 FRED API 金鑰...")
    fred_key_value = os.environ.get("FRED_API_KEY")

    if not fred_key_value or not fred_key_value.strip():
        print("INFO: [金鑰管理器] 未在環境變數中找到 FRED_API_KEY，跳過同步。")
        return

    key_hash = _hash_key(fred_key_value)

    # 檢查資料庫中是否已存在此金鑰
    if _execute_query("SELECT id FROM api_keys WHERE key_hash = ?", (key_hash,), fetch='one'):
        print(f"INFO: [金鑰管理器] FRED 金鑰 (雜湊值: ...{key_hash[-6:]}) 已存在於資料庫中，無需同步。")
        return

    print(f"INFO: [金鑰管理器] 偵測到新的 FRED 金鑰，正在將其新增至資料庫...")
    try:
        # 呼叫現有的 add_key 函式來新增金鑰
        add_key(
            key_value=fred_key_value,
            key_name="FRED 金鑰 (自動載入)",
            key_type='fred',
            validate=True  # 新增時立即驗證其有效性
        )
        print(f"SUCCESS: [金鑰管理器] 已成功新增並驗證 FRED 金鑰 (雜湊值: ...{key_hash[-6:]})。")
    except ValueError as e:
        # 這種情況理論上不應發生，因為我們已經檢查過雜湊值，但為了穩健性仍保留
        print(f"WARN: [金鑰管理器] 新增 FRED 金鑰時發生預期的錯誤（可能為已存在）: {e}")
    except Exception as e:
        # 捕獲其他潛在的資料庫或驗證錯誤
        print(f"ERROR: [金鑰管理器] 自動新增 FRED 金鑰時發生未預期的錯誤: {e}", file=sys.stderr)


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
