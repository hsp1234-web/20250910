# services/key_master_service/key_logic.py
import hashlib
from datetime import datetime
from typing import List, Optional, Dict, Any

# 從相鄰模組中匯入必要的函式和模型
from database import _execute_query
from models import KeyCreate, KeyInfo

def _hash_key(key: str) -> str:
    """對金鑰進行 SHA256 雜湊，只取前 16 位以便於使用。"""
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def upsert_key(key_data: KeyCreate) -> Dict[str, Any]:
    """
    新增或更新一個 API 金鑰 (UPSERT)。
    - 如果金鑰雜湊值已存在，則更新其 key_name 和 key_value。
    - 如果不存在，則新增一筆新紀錄。
    這可以有效防止 'UNIQUE constraint failed' 錯誤。
    """
    key_hash = _hash_key(key_data.key_value)
    now = datetime.now()

    # 1. 檢查金鑰是否已存在
    find_query = "SELECT id FROM api_keys WHERE key_hash = ?"
    existing_key = _execute_query(find_query, (key_hash,), fetch='one')

    if existing_key:
        # 2. 如果存在，執行 UPDATE
        # 注意：我們也更新 key_value，以防金鑰內容被輪換或修改
        query = """
            UPDATE api_keys
            SET key_name = ?, key_value = ?, key_type = ?, is_valid = ?, last_validated_at = ?
            WHERE key_hash = ?
        """
        # 在此簡化版本中，我們假設每次更新的金鑰都是有效的
        # 在未來可以加入驗證邏輯
        params = (key_data.key_name, key_data.key_value, key_data.key_type, True, now, key_hash)
        _execute_query(query, params)
        return {"message": "金鑰已成功更新。", "key_hash": key_hash}
    else:
        # 3. 如果不存在，執行 INSERT
        query = """
            INSERT INTO api_keys (key_name, key_type, key_hash, key_value, is_valid, last_validated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (key_data.key_name, key_data.key_type, key_hash, key_data.key_value, True, now)
        _execute_query(query, params)
        return {"message": "金鑰已成功新增。", "key_hash": key_hash}

def get_valid_key_by_type(key_type: str) -> Optional[str]:
    """
    根據類型從池中獲取一個有效的金鑰。
    策略：優先選取最久未被使用的活躍金鑰。
    """
    query = """
        SELECT id, key_value FROM api_keys
        WHERE key_type = ? AND is_valid = 1 AND status = 'active'
        ORDER BY last_used_at ASC NULLS FIRST
        LIMIT 1
    """
    key_row = _execute_query(query, (key_type,), fetch='one')

    if key_row:
        # 標記此金鑰為已使用
        update_query = "UPDATE api_keys SET last_used_at = ? WHERE id = ?"
        _execute_query(update_query, (datetime.now(), key_row["id"]))
        return key_row["key_value"]

    return None

def get_all_keys_info() -> List[KeyInfo]:
    """
    獲取所有金鑰的狀態資訊，但不包含原始金鑰值。
    """
    query = "SELECT key_name, key_type, key_hash, is_valid, last_validated_at FROM api_keys ORDER BY id"
    rows = _execute_query(query, fetch='all')
    if not rows:
        return []
    # 將 sqlite3.Row 物件明確轉換為字典，再交由 Pydantic 模型進行驗證
    # 這是為了解決 Pydantic v2 與 sqlite3.Row 的相容性問題
    return [KeyInfo.model_validate(dict(row)) for row in rows]

def delete_key_by_hash(key_hash: str) -> bool:
    """
    根據雜湊值從資料庫中刪除一個金鑰。
    """
    affected_rows = _execute_query("DELETE FROM api_keys WHERE key_hash = ?", (key_hash,))
    return affected_rows > 0