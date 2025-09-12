# src/core/key_manager.py
import json
import hashlib
import os
import sys
import subprocess
import logging
import threading
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

# --- Colab 環境安全匯入 ---
try:
    from google.colab import userdata
    IS_COLAB = True
except ImportError:
    IS_COLAB = False

# --- 路徑修正 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 常數 ---
SECRETS_DIR = SRC_DIR / "db" / "secrets"
KEYS_FILE = SECRETS_DIR / "keys.json"
IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"
ROOT_DIR = SRC_DIR.parent
log = logging.getLogger(__name__)

def _ensure_secrets_dir():
    """確保儲存金鑰的目錄存在。"""
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)

def _load_keys() -> List[Dict[str, Any]]:
    """從 JSON 檔案載入金鑰列表。"""
    _ensure_secrets_dir()
    if not KEYS_FILE.is_file():
        return []
    try:
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def _save_keys(keys: List[Dict[str, Any]]):
    """將金鑰列表儲存到 JSON 檔案。"""
    _ensure_secrets_dir()
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=4)

def _hash_key(key: str) -> str:
    """對金鑰進行 SHA256 雜湊，只取前 16 位以便於使用。"""
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def _validate_single_key(api_key: str) -> bool:
    """
    呼叫 gemini_processor.py 工具來驗證單一金鑰的有效性。
    """
    if IS_MOCK_MODE:
        # 在模擬模式下，任何非空金鑰都視為有效
        return bool(api_key)

    tool_script_path = ROOT_DIR / "src" / "tools" / "gemini_processor.py"
    cmd = [sys.executable, str(tool_script_path), "--command=validate_key"]

    minimal_env = {
        "PATH": os.environ.get("PATH", ""),
        "GOOGLE_API_KEY": api_key,
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")
    }
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', env=minimal_env, check=False)
        return result.returncode == 0
    except Exception:
        return False

def get_all_keys() -> List[Dict[str, Any]]:
    """獲取所有金鑰，但不包含金鑰本身，只包含其雜湊值和狀態。"""
    keys = _load_keys()
    # 為了安全，不直接回傳金鑰值
    return [
        {
            "name": key.get("name", f"Key-{i+1}"),
            "key_hash": key["key_hash"],
            "is_valid": key.get("is_valid"),
            "last_validated": key.get("last_validated")
        } for i, key in enumerate(keys)
    ]

def add_key(key_value: str, key_name: Optional[str] = None) -> Dict[str, Any]:
    """新增一個金鑰到金鑰池。"""
    if not key_value or not key_value.strip():
        raise ValueError("API 金鑰不可為空。")

    keys = _load_keys()
    key_hash = _hash_key(key_value)

    if any(k["key_hash"] == key_hash for k in keys):
        raise ValueError("此 API 金鑰已存在。")

    is_valid = _validate_single_key(key_value)

    new_key = {
        "name": key_name or f"Key-{len(keys) + 1}",
        "key_value": key_value, # 注意：儲存原始金鑰
        "key_hash": key_hash,
        "is_valid": is_valid,
        "last_validated": datetime.now().isoformat()
    }
    keys.append(new_key)
    _save_keys(keys)

    return {
        "name": new_key["name"],
        "key_hash": new_key["key_hash"],
        "is_valid": new_key["is_valid"]
    }

def delete_key(key_hash: str) -> bool:
    """根據雜湊值從金鑰池中刪除一個金鑰。"""
    keys = _load_keys()
    keys_before = len(keys)
    keys_after = [k for k in keys if k.get("key_hash") != key_hash]

    if len(keys_after) < keys_before:
        _save_keys(keys_after)
        return True
    return False

def validate_all_keys() -> List[Dict[str, Any]]:
    """重新驗證所有已儲存的金鑰。"""
    keys = _load_keys()
    for key in keys:
        key["is_valid"] = _validate_single_key(key["key_value"])
        key["last_validated"] = datetime.now().isoformat()
    _save_keys(keys)
    return get_all_keys()

def get_valid_key() -> Optional[str]:
    """從池中獲取一個有效的金鑰。"""
    keys = _load_keys()
    valid_keys = [k for k in keys if k.get("is_valid")]
    if not valid_keys:
        return None
    # 簡單輪詢策略
    return valid_keys[0]["key_value"]

def get_secret_with_retry(secret_name: str, max_attempts=3, timeout=10) -> (Optional[str], Optional[str]):
    """
    從 Colab userdata 安全地獲取金鑰，包含重試和超時機制。
    借鑒自使用者提供的 V48.8 程式碼。
    """
    for attempt in range(max_attempts):
        result = {"value": None, "error": None}
        def target():
            try:
                result["value"] = userdata.get(secret_name)
            except Exception as e:
                result["error"] = e
        thread = threading.Thread(target=target)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            error_msg = "讀取超時"
        elif result["error"]:
            error_msg = str(result["error"])
        else:
            return result["value"], None
        log.warning(f"讀取 Colab 金鑰 '{secret_name}' 失敗 (第 {attempt+1}/{max_attempts} 次): {error_msg}。")
        if attempt < max_attempts - 1:
            time.sleep((attempt + 1) * 2)
    return None, f"在 {max_attempts} 次嘗試後依然失敗"

def _load_keys_from_colab() -> List[Dict[str, str]]:
    """
    嘗試從 Colab Userdata 載入金鑰。
    如果成功，回傳 GeminiManager 所需的格式。
    如果失敗或不在 Colab 環境，回傳空列表。
    """
    if not IS_COLAB:
        return []

    log.info("偵測到 Colab 環境，嘗試從 Userdata 載入金鑰...")
    base_name = 'GOOGLE_API_KEY'
    # 嘗試讀取 GOOGLE_API_KEY, GOOGLE_API_KEY_1, ..., GOOGLE_API_KEY_15
    all_possible_names = [base_name] + [f"{base_name}_{i}" for i in range(1, 16)]

    valid_keys = []
    for name in all_possible_names:
        value, error = get_secret_with_retry(name)
        if value:
            log.info(f"成功從 Colab Userdata 讀取金鑰 '{name}'。")
            valid_keys.append({"name": name, "value": value})
        elif "is not defined" in (error or ""):
            # 這表示金鑰不存在，是正常情況，停止繼續尋找
            log.info(f"未在 Colab Userdata 中找到金鑰 '{name}'，停止搜尋。")
            break

    if valid_keys:
        log.info(f"已從 Colab Userdata 成功載入 {len(valid_keys)} 組金鑰。將優先使用這些金鑰。")
    else:
        log.info("未在 Colab Userdata 中找到任何金鑰。")

    return valid_keys

def get_all_valid_keys_for_manager() -> List[Dict[str, str]]:
    """
    獲取所有有效的金鑰，格式為 GeminiManager 所需的列表。
    格式: [{'name': 'key_name', 'value': 'key_value'}, ...]
    優先從 Colab Userdata 載入，如果失敗則從本地 JSON 檔案載入。
    """
    # 優先嘗試從 Colab 載入
    colab_keys = _load_keys_from_colab()
    if colab_keys:
        return colab_keys

    # 如果 Colab 中沒有金鑰，則退回使用本地檔案系統
    log.info("退回使用本地 JSON 檔案系統載入金鑰。")
    keys = _load_keys()
    valid_keys = [k for k in keys if k.get("is_valid")]

    manager_keys = [
        {"name": key.get("name", f"Key-{i+1}"), "value": key["key_value"]}
        for i, key in enumerate(valid_keys)
    ]

    if manager_keys:
        log.info(f"已從本地 JSON 檔案載入 {len(manager_keys)} 組有效金鑰。")
    else:
        log.warning("在任何位置（Colab Userdata 或本地 JSON）都找不到有效的 API 金鑰。")

    return manager_keys
