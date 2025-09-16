# src/core/key_health_manager.py
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timedelta, time
from typing import Optional, Any, Tuple

# --- 路徑設定 ---
# 確保此模組可以獨立運作，並找到資料庫
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))
DB_PATH = SRC_DIR / "db" / "database.sqlite3"

# --- 常數設定 ---
FROZEN_THRESHOLD = 10  # 連續進入冷卻狀態 10 次後觸發冷凍
TAIPEI_UTC_OFFSET = 8  # 台北時區為 UTC+8

# --- 核心資料庫輔助函式 (為保持模組獨立性，從 key_manager 複製) ---
def _execute_query(query: str, params: Tuple = (), fetch: Optional[str] = None) -> Any:
    """
    執行資料庫查詢的統一輔助函式。
    """
    # 增加 hasattr 檢查，以安全地處理測試中的 :memory: 資料庫路徑 (字串)
    if hasattr(DB_PATH, 'exists') and not DB_PATH.exists():
        # 在此 POC 階段，如果資料庫不存在，我們不拋出錯誤，而是記錄並返回
        print(f"錯誤: 資料庫檔案不存在於: {DB_PATH}。健康管理功能將無法運作。", file=sys.stderr)
        return None

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)

        if fetch == 'one':
            return cursor.fetchone()
        elif fetch == 'all':
            return cursor.fetchall()
        else:
            conn.commit()
            return cursor.rowcount
    except sqlite3.Error as e:
        print(f"資料庫錯誤: {e}\n查詢: {query}\n參數: {params}", file=sys.stderr)
        # 在 POC 階段，我們不重新拋出例外，避免中斷主流程
        return None
    finally:
        if conn:
            conn.close()

def _get_next_taipei_4am_utc() -> datetime:
    """
    計算下一個台北時間凌晨 4 點對應的 UTC 時間。
    不使用 pytz 以減少依賴。
    """
    now_utc = datetime.utcnow()
    now_taipei = now_utc + timedelta(hours=TAIPEI_UTC_OFFSET)

    # 檢查今天是否已經過了凌晨 4 點
    if now_taipei.time() >= time(4, 0):
        # 目標是明天的凌晨 4 點
        target_date = now_taipei.date() + timedelta(days=1)
    else:
        # 目標是今天的凌晨 4 點
        target_date = now_taipei.date()

    target_taipei_time = datetime.combine(target_date, time(4, 0))

    # 將台北時間轉換回 UTC
    target_utc_time = target_taipei_time - timedelta(hours=TAIPEI_UTC_OFFSET)
    return target_utc_time

def _set_key_frozen(key_hash: str):
    """
    內部函式：將金鑰狀態設定為 'frozen'。
    """
    frozen_until_dt = _get_next_taipei_4am_utc()
    frozen_until_iso = frozen_until_dt.isoformat()

    query = """
        UPDATE api_keys
        SET status = 'frozen', cooldown_count = 0, frozen_until = ?
        WHERE key_hash = ?
    """
    _execute_query(query, (frozen_until_iso, key_hash))
    print(f"金鑰 {key_hash[:8]}... 已被冷凍，直到 UTC 時間 {frozen_until_iso}")

# --- 公開 API ---

def record_key_error(key_hash: str):
    """
    記錄一次金鑰使用錯誤 (例如 429)。
    此函式會處理冷卻計數和可能的冷凍懲罰。
    """
    if not key_hash:
        return

    # 步驟 1: 獲取目前的冷卻次數
    key_info = _execute_query("SELECT cooldown_count FROM api_keys WHERE key_hash = ?", (key_hash,), fetch='one')
    if not key_info:
        print(f"健康管理員：找不到 key_hash 為 {key_hash} 的金鑰。", file=sys.stderr)
        return

    # 步驟 2: 計算新的冷卻次數
    new_cooldown_count = key_info['cooldown_count'] + 1

    # 步驟 3: 檢查是否達到冷凍閾值
    if new_cooldown_count >= FROZEN_THRESHOLD:
        _set_key_frozen(key_hash)
    else:
        # 僅增加計數並設定為 cooldown
        query = "UPDATE api_keys SET status = 'cooldown', cooldown_count = ? WHERE key_hash = ?"
        _execute_query(query, (new_cooldown_count, key_hash))
        print(f"金鑰 {key_hash[:8]}... 進入冷卻狀態，連續錯誤次數: {new_cooldown_count}")

def record_key_success(key_hash: str):
    """
    記錄一次金鑰成功使用。
    這將會重設金鑰的狀態為 'active'，並清除冷卻計數。
    """
    if not key_hash:
        return

    # 只在金鑰目前不是 'active' 狀態時才進行更新，以減少不必要的資料庫寫入
    query = """
        UPDATE api_keys
        SET status = 'active', cooldown_count = 0
        WHERE key_hash = ? AND status != 'active'
    """
    _execute_query(query, (key_hash,))
