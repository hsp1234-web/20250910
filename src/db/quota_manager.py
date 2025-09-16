# src/db/quota_manager.py
import sqlite3
import sys
from pathlib import Path
from typing import List, Dict, Any

# --- 路徑設定 ---
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from core.key_manager import _execute_query

def get_all_quotas() -> List[Dict[str, Any]]:
    """
    從資料庫中獲取所有模型的流量限制設定。
    """
    query = "SELECT model_name, rpm, tpm, rpd FROM model_quotas ORDER BY model_name"
    rows = _execute_query(query, fetch='all')
    # 將 sqlite3.Row 物件轉換為標準字典
    return [dict(row) for row in rows]

def update_quotas(quotas: List[Dict[str, Any]]) -> int:
    """
    更新一或多個模型的流量限制設定。
    使用 INSERT OR REPLACE (UPSERT) 語法。
    """
    if not quotas:
        return 0

    query = """
        INSERT OR REPLACE INTO model_quotas (model_name, rpm, tpm, rpd)
        VALUES (:model_name, :rpm, :tpm, :rpd)
    """

    # _execute_query 目前不支援 executemany，我們先手動實現
    conn = sqlite3.connect(Path(SRC_DIR) / "db" / "database.sqlite3", timeout=10)
    try:
        cursor = conn.cursor()
        # executemany 會自動處理事務
        cursor.executemany(query, quotas)
        conn.commit()
        return cursor.rowcount
    except sqlite3.Error as e:
        print(f"資料庫錯誤: {e}", file=sys.stderr)
        conn.rollback()
        raise
    finally:
        conn.close()

def get_quota_for_model(model_name: str) -> Dict[str, Any]:
    """
    獲取單一模型的流量限制設定。
    """
    query = "SELECT model_name, rpm, tpm, rpd FROM model_quotas WHERE model_name = ?"
    row = _execute_query(query, params=(model_name,), fetch='one')
    return dict(row) if row else None
