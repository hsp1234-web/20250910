# src/core/key_manager.py
import json
import hashlib
import os
import sys
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime
import logging

# --- 路徑修正 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 常數與設定 ---
SECRETS_DIR = SRC_DIR / "db" / "secrets"
KEYS_FILE = SECRETS_DIR / "keys.json"
ROOT_DIR = SRC_DIR.parent
log = logging.getLogger(__name__)

# --- 全域狀態 ---
# 這個旗標用於判斷金鑰是否從環境變數載入，若是，則禁用檔案寫入操作。
_KEYS_LOADED_FROM_ENV = False
# 記憶體快取，避免重複讀取檔案或解析環境變數。
_cached_keys = None

def _hash_key(key: str) -> str:
    """對金鑰進行 SHA256 雜湊，只取前 16 位以便於使用。"""
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def _load_keys_from_env() -> Optional[List[Dict[str, Any]]]:
    """嘗試從環境變數 GOOGLE_API_KEYS_JSON 載入金鑰。"""
    keys_json_str = os.environ.get("GOOGLE_API_KEYS_JSON")
    if not keys_json_str:
        return None

    log.info("偵測到來自環境變數的金鑰，將優先使用此來源。")
    try:
        keys_from_env = json.loads(keys_json_str)
        processed_keys = []
        for i, key_data in enumerate(keys_from_env):
            key_value = key_data.get("value")
            if not key_value:
                continue

            # 因為金鑰來自受信任的啟動器 (Colab Secrets)，我們預設其為有效
            processed_keys.append({
                "name": key_data.get("name", f"Secret-Key-{i+1}"),
                "key_value": key_value,
                "key_hash": _hash_key(key_value),
                "is_valid": True,
                "last_validated": datetime.now().isoformat()
            })

        global _KEYS_LOADED_FROM_ENV
        _KEYS_LOADED_FROM_ENV = True
        return processed_keys
    except json.JSONDecodeError:
        log.error("解析來自環境變數的 JSON 金鑰時發生錯誤。")
        return []

def _load_keys_from_file() -> List[Dict[str, Any]]:
    """從 JSON 檔案載入金鑰列表。"""
    _ensure_secrets_dir()
    if not KEYS_FILE.is_file():
        return []
    try:
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def _get_keys() -> List[Dict[str, Any]]:
    """
    獲取金鑰的主函式，帶有記憶體快取。
    優先從環境變數載入，若無則從檔案載入。
    """
    global _cached_keys
    if _cached_keys is not None:
        return _cached_keys

    keys = _load_keys_from_env()
    if keys is None:
        keys = _load_keys_from_file()

    _cached_keys = keys
    return keys

def _save_keys(keys: List[Dict[str, Any]]):
    """將金鑰列表儲存到 JSON 檔案，但如果金鑰是從環境變數載入的，則會阻止此操作。"""
    if _KEYS_LOADED_FROM_ENV:
        log.warning("金鑰由環境變數管理，已阻止對 keys.json 的寫入操作。")
        return

    _ensure_secrets_dir()
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=4)

    # 更新快取
    global _cached_keys
    _cached_keys = keys

def _ensure_secrets_dir():
    """確保儲存金鑰的目錄存在。"""
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)

def _validate_single_key(api_key: str) -> bool:
    """呼叫 gemini_processor.py 工具來驗證單一金鑰的有效性。"""
    tool_script_path = ROOT_DIR / "src" / "tools" / "gemini_processor.py"
    cmd = [sys.executable, str(tool_script_path), "--command=validate_key"]
    minimal_env = {"PATH": os.environ.get("PATH", ""), "GOOGLE_API_KEY": api_key, "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', env=minimal_env, check=False)
        return result.returncode == 0
    except Exception:
        return False

def get_all_keys() -> List[Dict[str, Any]]:
    """獲取所有金鑰，但不包含金鑰本身，只包含其雜湊值和狀態。"""
    keys = _get_keys()
    return [{"name": key.get("name", f"Key-{i+1}"), "key_hash": key["key_hash"], "is_valid": key.get("is_valid"), "last_validated": key.get("last_validated")} for i, key in enumerate(keys)]

def add_key(key_value: str, key_name: Optional[str] = None) -> Dict[str, Any]:
    """新增一個金鑰到金鑰池，並立即進行驗證。"""
    if _KEYS_LOADED_FROM_ENV:
        raise PermissionError("金鑰由環境變數管理，無法透過 API 新增。")
    if not key_value or not key_value.strip():
        raise ValueError("API 金鑰不可為空。")

    keys = _get_keys()
    key_hash = _hash_key(key_value)

    if any(k["key_hash"] == key_hash for k in keys):
        raise ValueError("此 API 金鑰已存在。")

    is_valid = _validate_single_key(key_value)
    new_key = {"name": key_name or f"Key-{len(keys) + 1}", "key_value": key_value, "key_hash": key_hash, "is_valid": is_valid, "last_validated": datetime.now().isoformat()}
    keys.append(new_key)
    _save_keys(keys)
    return {"name": new_key["name"], "key_hash": new_key["key_hash"], "is_valid": new_key["is_valid"]}

def test_key(api_key: str) -> bool:
    """測試單一 API 金鑰的有效性，而不將其儲存。"""
    return _validate_single_key(api_key) if api_key else False

def delete_key(key_hash: str) -> bool:
    """根據雜湊值從金鑰池中刪除一個金鑰。"""
    if _KEYS_LOADED_FROM_ENV:
        raise PermissionError("金鑰由環境變數管理，無法透過 API 刪除。")

    keys = _get_keys()
    original_count = len(keys)
    keys_after_deletion = [k for k in keys if k.get("key_hash") != key_hash]

    if len(keys_after_deletion) < original_count:
        _save_keys(keys_after_deletion)
        return True
    return False

def validate_all_keys() -> List[Dict[str, Any]]:
    """重新驗證所有已儲存的金鑰。"""
    if _KEYS_LOADED_FROM_ENV:
        log.info("金鑰由環境變數管理，跳過檔案驗證。")
        return get_all_keys()

    keys = _get_keys()
    for key in keys:
        key["is_valid"] = _validate_single_key(key["key_value"])
        key["last_validated"] = datetime.now().isoformat()
    _save_keys(keys)
    return get_all_keys()

def get_valid_key() -> Optional[str]:
    """從池中獲取一個有效的金鑰。"""
    keys = _get_keys()
    valid_keys = [k for k in keys if k.get("is_valid")]
    return valid_keys[0]["key_value"] if valid_keys else None

def get_all_valid_keys_for_manager() -> List[Dict[str, str]]:
    """獲取所有有效的金鑰，格式為 GeminiManager 所需的列表。"""
    keys = _get_keys()
    valid_keys = [k for k in keys if k.get("is_valid")]
    return [{"name": key.get("name", f"Key-{i+1}"), "value": key["key_value"]} for i, key in enumerate(valid_keys)]
