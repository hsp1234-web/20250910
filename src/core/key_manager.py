# src/core/key_manager.py
import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Optional

# --- 路徑修正 ---
# 確保 db 模組可以被正確匯入
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

# 由於這個模組現在需要與資料庫互動，我們需要匯入資料庫函式
from db import database as db

log = logging.getLogger(__name__)

class KeyManager:
    """
    一個基於資料庫的智慧型 API 金鑰管理器。
    負責從環境變數載入金鑰、將金鑰值安全地儲存在記憶體中、
    並透過資料庫來管理金鑰的狀態（活躍、冷卻、禁用）。
    """
    def __init__(self):
        # 金鑰的實際值只儲存在記憶體中，絕不存入資料庫。
        self._key_values: Dict[str, str] = {}
        log.info("KeyManager 已初始化。")

    def sync_keys_from_environment(self, count: int = 10) -> Dict:
        """
        從環境變數讀取 GOOGLE_API_KEY... 系列金鑰，
        將其值存入記憶體，並將其名稱同步到資料庫。
        """
        log.info(f"正在從環境變數中同步最多 {count} 組 API 金鑰...")
        base_key_name = "GOOGLE_API_KEY"
        target_key_names = [base_key_name]
        if count > 0:
            target_key_names.extend([f"{base_key_name}_{i}" for i in range(1, count + 1)])

        found_keys = {}
        for name in target_key_names:
            value = os.environ.get(name)
            if value:
                found_keys[name] = value

        if not found_keys:
            log.warning("在環境變數中沒有找到任何 GOOGLE_API_KEY。")
            return {"status": "未找到任何金鑰"}

        # 將金鑰值存入記憶體
        self._key_values.update(found_keys)
        log.info(f"已從環境變數載入 {len(found_keys)} 組金鑰到記憶體。")

        # 將金鑰名稱同步到資料庫
        key_names_list = list(found_keys.keys())
        success = db.sync_api_keys(key_names_list)

        return {
            "status": "同步成功" if success else "同步失敗",
            "found_keys": len(found_keys),
            "synced_to_db": key_names_list
        }

    def add_key_manually(self, key_name: str, key_value: str) -> bool:
        """
        手動新增單一金鑰，用於手動貼上等情境。
        """
        if not key_name or not key_value:
            log.error("手動新增金鑰失敗：金鑰名稱和值不可為空。")
            return False

        # 1. 將金鑰值存入記憶體
        self._key_values[key_name] = key_value
        log.info(f"已將手動金鑰 '{key_name}' 存入記憶體。")

        # 2. 將金鑰名稱同步到資料庫
        success = db.sync_api_keys([key_name])
        if success:
            log.info(f"已成功將手動金鑰 '{key_name}' 同步到資料庫。")
        else:
            log.error(f"手動金鑰 '{key_name}' 同步到資料庫失敗。")

        return success

    def get_key(self) -> Optional[Dict[str, str]]:
        """
        獲取一個可用的 API 金鑰。
        這是給 GeminiManager 呼叫的主要函式。
        """
        # 從資料庫獲取一個可用金鑰的名稱
        key_name = db.get_available_api_key()

        if not key_name:
            log.error("無法獲取可用金鑰：所有金鑰可能都在冷卻中或已被禁用。")
            return None

        # 從記憶體中查找對應的金鑰值
        key_value = self._key_values.get(key_name)
        if not key_value:
            log.error(f"資料庫回傳金鑰 '{key_name}'，但在記憶體中找不到其對應的值！請檢查同步過程。")
            return None

        log.info(f"提供金鑰 '{key_name}' 供外部使用。")
        return {"name": key_name, "value": key_value}

    def set_key_cooldown(self, key_name: str, cooldown_seconds: int):
        """
        通知管理器將某個金鑰置於冷卻狀態。
        """
        log.warning(f"外部請求將金鑰 '{key_name}' 設為冷卻 {cooldown_seconds} 秒。")
        db.set_api_key_cooldown(key_name, cooldown_seconds)

    def get_key_statuses(self) -> List[Dict]:
        """
        從資料庫獲取所有金鑰的狀態，用於儀表板顯示。
        """
        return db.get_all_api_key_statuses()

    def update_key_status(self, key_name: str, status: str) -> bool:
        """
        手動更新金鑰狀態（例如：禁用）。
        """
        return db.update_key_status_manually(key_name, status)

    def reset_all_keys_status(self) -> bool:
        """
        重設所有金鑰的狀態為 'active'。
        """
        log.info("請求重設所有金鑰狀態為 active...")
        return db.reset_all_keys_to_active()

# 建立一個全域實例，使其在應用程式中像單例一樣運作
key_manager = KeyManager()
