import json
import logging
from pathlib import Path
from typing import Dict, Any

# --- 路徑設定 ---
# 專案根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
# 設定檔路徑
CONFIG_FILE = ROOT_DIR / "config" / "config.json"
# 設定檔範本路徑
CONFIG_TEMPLATE_FILE = ROOT_DIR / "config" / "config.json.template"

log = logging.getLogger(__name__)

_config_cache: Dict[str, Any] = {}

def _load_config() -> Dict[str, Any]:
    """
    從 config.json 載入設定。如果檔案不存在，則從範本建立。
    實現了簡單的快取機制，避免重複讀取檔案。
    """
    global _config_cache
    if _config_cache:
        return _config_cache

    if not CONFIG_FILE.exists():
        log.warning(f"設定檔 {CONFIG_FILE} 不存在，將從範本 {CONFIG_TEMPLATE_FILE} 建立。")
        if not CONFIG_TEMPLATE_FILE.exists():
            log.error(f"設定檔範本 {CONFIG_TEMPLATE_FILE} 也不存在！無法建立設定。")
            # 在此情況下，回傳一個包含預設超時的空字典，以避免啟動失敗
            _config_cache = {"api_timeout_seconds": 35}
            return _config_cache

        try:
            template_content = CONFIG_TEMPLATE_FILE.read_text(encoding="utf-8")
            CONFIG_FILE.write_text(template_content, encoding="utf-8")
            log.info(f"已成功從範本建立設定檔: {CONFIG_FILE}")
            _config_cache = json.loads(template_content)
        except (IOError, json.JSONDecodeError) as e:
            log.error(f"從範本建立設定檔時發生錯誤: {e}", exc_info=True)
            # 即使建立失敗，也提供一個預設值
            _config_cache = {"api_timeout_seconds": 35}
            return _config_cache
    else:
        try:
            config_content = CONFIG_FILE.read_text(encoding="utf-8")
            _config_cache = json.loads(config_content)
        except (IOError, json.JSONDecodeError) as e:
            log.error(f"讀取設定檔 {CONFIG_FILE} 時發生錯誤: {e}", exc_info=True)
            # 讀取失敗時，回退到範本
            return _load_config_from_template_as_fallback()

    return _config_cache

def _load_config_from_template_as_fallback() -> Dict[str, Any]:
    """當主設定檔讀取失敗時，作為後備從範本檔案載入設定。"""
    global _config_cache
    log.warning("作為後備，嘗試從範本檔案載入設定。")
    try:
        template_content = CONFIG_TEMPLATE_FILE.read_text(encoding="utf-8")
        _config_cache = json.loads(template_content)
        return _config_cache
    except (IOError, json.JSONDecodeError) as e:
        log.error(f"後備方案：從範本檔案 {CONFIG_TEMPLATE_FILE} 讀取設定也失敗了: {e}", exc_info=True)
        _config_cache = {"api_timeout_seconds": 35} # 最後的防線
        return _config_cache


def get_config() -> Dict[str, Any]:
    """
    獲取目前載入的設定。
    這是外部模組應使用的主要函式。
    """
    return _load_config()

def save_config(new_config: Dict[str, Any]) -> bool:
    """
    將新的設定物件儲存回 config.json 檔案。
    """
    global _config_cache
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(new_config, f, indent=4, ensure_ascii=False)
        _config_cache = new_config  # 更新快取
        log.info(f"設定已成功儲存至 {CONFIG_FILE}")
        return True
    except IOError as e:
        log.error(f"儲存設定至 {CONFIG_FILE} 時發生 I/O 錯誤: {e}", exc_info=True)
        return False

def get_config_value(key: str, default: Any = None) -> Any:
    """
    安全地獲取設定檔中特定鍵的值。
    """
    config = get_config()
    return config.get(key, default)

def update_config_value(key: str, value: Any) -> bool:
    """
    更新設定檔中特定鍵的值並儲存。
    """
    current_config = get_config().copy()
    current_config[key] = value
    return save_config(current_config)

if __name__ == '__main__':
    # 簡單的測試
    print("--- 測試設定管理器 ---")

    # 模擬檔案不存在的情況
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
    if "api_timeout_seconds" in _config_cache:
        del _config_cache["api_timeout_seconds"]

    print(f"設定檔是否存在: {CONFIG_FILE.exists()}")

    # 1. 第一次載入 (應從範本建立)
    config = get_config()
    print(f"第一次載入的設定: {config}")
    print(f"設定檔現在是否存在: {CONFIG_FILE.exists()}")

    # 2. 獲取特定值
    timeout = get_config_value("api_timeout_seconds", 99)
    print(f"獲取到的超時設定: {timeout}")

    # 3. 更新特定值
    print("正在更新超時設定為 45...")
    update_config_value("api_timeout_seconds", 45)

    # 4. 重新載入並驗證
    _config_cache = {} # 清除快取以強制重新讀取
    new_config = get_config()
    print(f"更新後重新載入的設定: {new_config}")
    print(f"驗證更新: {'成功' if new_config.get('api_timeout_seconds') == 45 else '失敗'}")

    # 還原
    update_config_value("api_timeout_seconds", 35)
    print("已還原超時設定為 35。")
    print("--- 測試結束 ---")
