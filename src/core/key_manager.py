# src/core/key_manager.py
import hashlib
import os
import sqlite3
import sys
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))
ROOT_DIR = SRC_DIR.parent

def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def _validate_single_key(api_key: str) -> bool:
    tool_script_path = ROOT_DIR / "src" / "tools" / "gemini_processor.py"
    cmd = [sys.executable, str(tool_script_path), "--command=validate_key"]
    env = os.environ.copy()
    env["GOOGLE_API_KEY"] = api_key
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', env=env, check=False, timeout=20)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False

def _validate_fred_key(api_key: str) -> bool:
    import fredapi
    if not api_key:
        return False
    try:
        fred = fredapi.Fred(api_key=api_key)
        fred.get_series_info('GNP')
        return True
    except Exception:
        return False

def get_all_keys(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT key_name, key_hash, key_type, is_valid, last_validated_at, total_tokens_used FROM api_keys ORDER BY id")
    rows = cursor.fetchall()
    return [{"name": row["key_name"], "key_hash": row["key_hash"], "key_type": row["key_type"], "is_valid": bool(row["is_valid"]), "last_validated": row["last_validated_at"], "total_tokens_used": row["total_tokens_used"]} for row in rows]

def add_key(conn: sqlite3.Connection, key_value: str, key_name: Optional[str] = None, key_type: str = 'gemini', validate: bool = True) -> Dict[str, Any]:
    if not key_value or not key_value.strip():
        raise ValueError("API 金鑰不可為空。")
    if key_type not in ['gemini', 'fred']:
        raise ValueError("無效的金鑰類型。必須是 'gemini' 或 'fred'。")
    key_hash = _hash_key(key_value)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM api_keys WHERE key_hash = ?", (key_hash,))
    if cursor.fetchone():
        raise ValueError("此 API 金鑰已存在。")
    is_valid = False
    validation_time = None
    if validate:
        validation_time = datetime.now().isoformat()
        if key_type == 'gemini':
            is_valid = _validate_single_key(key_value)
        elif key_type == 'fred':
            is_valid = _validate_fred_key(key_value)
    final_key_name = key_name or f"{key_type.capitalize()}-Key-{int(time.time())}"
    cursor.execute("INSERT INTO api_keys (key_name, key_hash, key_value, key_type, is_valid, last_validated_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)", (final_key_name, key_hash, key_value, key_type, is_valid, validation_time, 'active'))
    conn.commit()
    return {"name": final_key_name, "key_hash": key_hash, "key_type": key_type, "is_valid": is_valid}

def delete_key(conn: sqlite3.Connection, key_hash: str) -> bool:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM api_keys WHERE key_hash = ?", (key_hash,))
    conn.commit()
    return cursor.rowcount > 0

def clear_all_keys(conn: sqlite3.Connection) -> int:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='api_keys'")
    cursor.execute("DELETE FROM api_keys")
    conn.commit()
    return cursor.rowcount

def validate_all_keys(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, key_value, key_type FROM api_keys")
    keys_to_validate = cursor.fetchall()
    if not keys_to_validate:
        return []
    validator_map: Dict[str, Callable[[str], bool]] = {'gemini': _validate_single_key, 'fred': _validate_fred_key}
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_key_id = {}
        for key in keys_to_validate:
            validator = validator_map.get(key["key_type"])
            if validator:
                future = executor.submit(validator, key["key_value"])
                future_to_key_id[future] = key["id"]
            else:
                print(f"警告：金鑰 ID {key['id']} 的類型 '{key['key_type']}' 沒有對應的驗證器，已跳過。", file=sys.stderr)
        for future in as_completed(future_to_key_id):
            key_id = future_to_key_id[future]
            try:
                is_valid = future.result()
                validation_time = datetime.now().isoformat()
                cursor.execute("UPDATE api_keys SET is_valid = ?, last_validated_at = ? WHERE id = ?", (is_valid, validation_time, key_id))
                conn.commit()
            except Exception as exc:
                print(f"處理金鑰 ID {key_id} 的驗證時產生錯誤: {exc}", file=sys.stderr)
    return get_all_keys(conn)

def get_key_by_type(conn: sqlite3.Connection, key_type: str) -> Optional[str]:
    if not key_type:
        return None
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, key_value FROM api_keys WHERE status = 'active' AND is_valid = 1 AND key_type = ? ORDER BY last_used_at ASC NULLS FIRST LIMIT 1", (key_type,))
    key_row = cursor.fetchone()
    if key_row:
        cursor.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (datetime.now().isoformat(), key_row["id"]))
        conn.commit()
        return key_row["key_value"]
    return None

def get_all_valid_keys_for_manager(conn: sqlite3.Connection) -> List[Dict[str, str]]:
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT key_name, key_value FROM api_keys WHERE is_valid = 1 AND status = 'active' AND key_type = 'gemini'")
    rows = cursor.fetchall()
    return [{"name": row["key_name"], "value": row["key_value"]} for row in rows]

def test_key(api_key: str, key_type: str = 'gemini') -> bool:
    if not api_key:
        return False
    if key_type == 'gemini':
        return _validate_single_key(api_key)
    elif key_type == 'fred':
        return _validate_fred_key(api_key)
    return False

def add_keys_from_environment(conn: sqlite3.Connection, count: int) -> Dict[str, Any]:
    if not isinstance(count, int) or count < 0:
        raise ValueError("金鑰數量必須是一個非負整數。")
    base_key_name = "GOOGLE_API_KEY"
    target_key_names = [base_key_name]
    if count > 0:
        target_key_names.extend([f"{base_key_name}_{i}" for i in range(1, count + 1)])
    summary = {"total_attempted": len(target_key_names), "successfully_added": 0, "already_existed": 0, "not_found": 0, "invalid_keys": 0, "details": []}
    for key_name in target_key_names:
        key_value = os.environ.get(key_name)
        if not key_value:
            summary["not_found"] += 1
            summary["details"].append({"name": key_name, "status": "未在環境變數中找到"})
            continue
        try:
            result = add_key(conn, key_value, key_name)
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

def record_token_usage(conn: sqlite3.Connection, key_name: str, tokens_used: int):
    if not key_name or tokens_used is None or tokens_used < 0:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE api_keys SET total_tokens_used = total_tokens_used + ?, request_count = request_count + 1 WHERE key_name = ?", (tokens_used, key_name))
        conn.commit()
    except Exception as e:
        print(f"警告：記錄金鑰 '{key_name}' 的 token 使用量時發生錯誤: {e}", file=sys.stderr)
