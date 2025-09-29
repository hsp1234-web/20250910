# services/key_master_service/main.py
import sys
from pathlib import Path

# JULES'S FINAL FIX (2025-09-29): 解決 ModuleNotFoundError 的終極方案
# 將此檔案所在的目錄明確地加入到 Python 的系統路徑中。
# 這樣一來，無論 uvicorn 是如何啟動這個 main:app，
# Python 解譯器都能找到 key_logic, database, models 等同級模組。
SERVICE_DIR = Path(__file__).resolve().parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.append(str(SERVICE_DIR))

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from typing import List

# 簡單、非相對的匯入，適用於在服務自身目錄下運行的標準微服務實踐
import key_logic
import database
from models import KeyCreate, KeyInfo, UpsertResponse, ValidKeyResponse

# --- FastAPI 應用程式實例 ---
app = FastAPI(
    title="Key Master Service",
    description="一個用於集中管理、輪換和提供 API 金鑰的微服務。",
    version="1.0.0"
)

# --- CORS 中介軟體設定 ---
# 為了允許前端頁面 (來自 8000 埠) 能夠呼叫此服務 (在 8008 埠)，我們需要啟用跨來源資源共用。
# 在生產環境中，應將 "allow_origins" 設定為特定的前端網域以策安全。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允許所有來源，在開發環境中通常是安全的
    allow_credentials=True,
    allow_methods=["*"],  # 允許所有 HTTP 方法 (GET, POST, etc.)
    allow_headers=["*"],  # 允許所有請求標頭
)

# --- 應用程式生命週期事件 ---

@app.on_event("startup")
def on_startup():
    """
    在應用程式啟動時執行的函式。
    主要任務是確保資料庫和必要的資料表都已建立。
    """
    database.create_db_and_tables()

# --- API 端點 (Endpoints) ---

@app.post("/api/v1/keys", response_model=UpsertResponse, status_code=status.HTTP_201_CREATED,
          summary="新增或更新一個 API 金鑰 (Upsert)",
          description="如果金鑰已存在（根據其雜湊值），則更新其資訊；否則，建立一個新的金鑰紀錄。")
def upsert_api_key(key_data: KeyCreate):
    """
    處理新增或更新 API 金鑰的請求。
    """
    try:
        result = key_logic.upsert_key(key_data)
        # 根據操作是新增還是更新，設定不同的狀態碼
        if "更新" in result["message"]:
            return UpsertResponse(**result)
        else:
            # 這裡為了符合 RESTful 風格，可以回傳 201 Created
            # 但為了簡化，我們統一回傳 UpsertResponse
            return UpsertResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"處理金鑰時發生錯誤: {e}")

@app.get("/api/v1/keys/{key_type}/valid", response_model=ValidKeyResponse,
         summary="獲取一個指定類型的有效金鑰",
         description="從金鑰池中輪換獲取一個當前有效且可用的 API 金鑰。")
def get_valid_api_key(key_type: str):
    """
    提供一個可用於外部服務呼叫的有效金鑰。
    """
    key_value = key_logic.get_valid_key_by_type(key_type)
    if not key_value:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"目前沒有可用的 '{key_type}' 類型有效金鑰。"
        )
    return ValidKeyResponse(key_value=key_value)

@app.get("/api/v1/keys", response_model=List[KeyInfo],
         summary="列出所有金鑰的資訊",
         description="獲取資料庫中所有金鑰的狀態資訊，出於安全考量，此回應不包含金鑰的實際值。")
def list_all_keys():
    """
    回傳所有被管理金鑰的列表。
    """
    return key_logic.get_all_keys_info()

@app.delete("/api/v1/keys/{key_hash}", status_code=status.HTTP_204_NO_CONTENT,
            summary="刪除一個指定的金鑰",
            description="根據金鑰的 SHA256 雜湊值（前16碼）將其從資料庫中永久刪除。")
def delete_api_key(key_hash: str):
    """
    根據金鑰雜湊值刪除金鑰。
    """
    success = key_logic.delete_key_by_hash(key_hash)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到雜湊值為 '{key_hash}' 的金鑰。"
        )
    # 成功刪除後，回傳 204 No Content，不需要 body
    return