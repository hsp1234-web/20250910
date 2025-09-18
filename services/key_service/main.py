# services/key_service/main.py
# 金鑰管理微服務：一個功能完整、獨立的服務。
import hashlib
import sqlite3
import time
import os
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime

# 依賴
from fastapi import FastAPI, APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
import uvicorn
import google.generativeai as genai
import google.api_core.exceptions

# --- 設定與全域變數 ---
SERVICE_NAME = "KeyService"
POC_DIR = Path(__file__).resolve().parent
DB_PATH = POC_DIR / "key_service.db"

# 使用 print 作為簡單的日誌記錄器，並加上服務名前綴
def log(message, level="INFO"):
    print(f"[{level}][{SERVICE_NAME}] {message}")

# --- 1. 資料庫初始化 ---
def setup_database():
    """建立並初始化一個本地的 SQLite 資料庫和資料表。"""
    if DB_PATH.exists():
        return
    log(f"正在為服務建立新的資料庫於: {DB_PATH}")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_name TEXT NOT NULL UNIQUE,
            key_hash TEXT NOT NULL UNIQUE,
            key_value TEXT NOT NULL,
            is_valid INTEGER NOT NULL DEFAULT 0,
            last_validated_at TEXT,
            last_used_at TEXT,
            total_tokens_used INTEGER DEFAULT 0,
            request_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active'
        );
        """)
        conn.commit()
        conn.close()
        log(f"資料庫和 'api_keys' 資料表已成功建立。")
    except sqlite3.Error as e:
        log(f"資料庫設定失敗: {e}", "ERROR")
        raise

# --- 2. 核心邏輯 (移植自 key_manager 和 gemini_processor) ---

# 2a. 資料庫操作
def _execute_query(query: str, params: Tuple = (), fetch: Optional[str] = None) -> Any:
    """執行資料庫查詢的統一輔助函式。"""
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
        log(f"資料庫錯誤: {e}", "ERROR")
        raise
    finally:
        if conn:
            conn.close()

# 2b. 金鑰驗證 (直接呼叫，不再使用 subprocess)
def validate_key_direct(api_key: str) -> bool:
    """
    直接呼叫 Google AI SDK 來驗證金鑰的有效性。
    移植自 gemini_processor.py 的核心邏輯。
    """
    if not api_key:
        return False
    try:
        genai.configure(api_key=api_key)
        # 執行一個輕量級的 API 呼叫來觸發驗證
        next(genai.list_models(), None)
        return True
    except (google.api_core.exceptions.InvalidArgument, google.api_core.exceptions.PermissionDenied) as e:
        log(f"金鑰驗證失敗: {e}", "WARN")
        return False
    except Exception as e:
        log(f"金鑰驗證時發生未預期的網路或其他錯誤：{e}", "WARN")
        return False

# 2c. 金鑰管理邏輯
def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def get_all_keys() -> List[Dict[str, Any]]:
    """獲取所有金鑰的狀態。"""
    rows = _execute_query("SELECT key_name, key_hash, is_valid, last_validated_at FROM api_keys", fetch='all')
    return [dict(row) for row in rows] if rows else []

def add_key(key_value: str, key_name: Optional[str] = None) -> Dict[str, Any]:
    """新增一個金鑰到資料庫，並使用直接驗證函式。"""
    if not key_value or not key_value.strip():
        raise ValueError("API 金鑰不可為空。")
    key_hash = _hash_key(key_value)
    if _execute_query("SELECT id FROM api_keys WHERE key_hash = ?", (key_hash,), fetch='one'):
        raise ValueError("此 API 金鑰已存在。")

    is_valid = validate_key_direct(key_value)
    validation_time = datetime.now().isoformat()
    final_key_name = key_name or f"Key-{int(time.time())}"

    query = "INSERT INTO api_keys (key_name, key_hash, key_value, is_valid, last_validated_at) VALUES (?, ?, ?, ?, ?)"
    _execute_query(query, (final_key_name, key_hash, key_value, is_valid, validation_time))
    return {"name": final_key_name, "key_hash": key_hash, "is_valid": is_valid}

def delete_key(key_hash: str) -> bool:
    """根據雜湊值從資料庫中刪除一個金鑰。"""
    affected_rows = _execute_query("DELETE FROM api_keys WHERE key_hash = ?", (key_hash,))
    return affected_rows > 0

# --- 3. API 路由 (移植自 page6_keys.py) ---

router = APIRouter()

class KeyModel(BaseModel):
    api_key: str = Field(..., title="Google API Key")
    name: Optional[str] = Field(None, title="Key Alias")

@router.get("/keys", summary="獲取所有金鑰的狀態")
async def get_keys_status_api():
    return get_all_keys()

@router.post("/keys", summary="新增並驗證一個 API 金鑰")
async def add_new_key_api(payload: KeyModel):
    try:
        result = add_key(payload.api_key, payload.name)
        return {"message": f"金鑰 '{result['name']}' 已新增。", **result}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        log(f"新增金鑰時發生錯誤: {e}", "ERROR")
        raise HTTPException(status_code=500, detail="伺服器內部錯誤。")

@router.delete("/keys/{key_hash}", summary="刪除指定的 API 金鑰")
async def remove_key_api(key_hash: str):
    if delete_key(key_hash):
        return {"message": "金鑰已成功刪除。"}
    else:
        raise HTTPException(status_code=404, detail="找不到具有該雜湊值的金鑰。")

# --- 4. FastAPI 應用主體 ---

app = FastAPI(
    title=SERVICE_NAME,
    description="一個用於管理和驗證 API 金鑰的獨立微服務。",
    version="1.0.0"
)

app.include_router(router, prefix="/api")

@app.on_event("startup")
def on_startup():
    setup_database()

@app.get("/", summary="健康檢查端點")
def read_root():
    return {"status": f"{SERVICE_NAME} is running"}

# --- 允許直接執行此檔案以進行測試 ---
if __name__ == "__main__":
    # 從環境變數讀取埠號，以便協調器可以動態指派
    port = int(os.environ.get("PORT", 8001))
    log(f"將在 http://127.0.0.1:{port} 上啟動伺服器")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
