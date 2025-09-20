# services/bond_data_service/main.py

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import database
from data_manager import DataManager

# --- Global instances ---
data_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global data_manager
    # 在應用啟動時執行的程式碼
    print("Bond Data Service is starting up...")
    database.initialize_database()

    # 從環境變數讀取 API 金鑰，若無則使用後備金鑰
    api_key = os.getenv("FRED_API_KEY", "77b0a570c6a17007e4f5af229c2aecc9")
    if not api_key:
        raise ValueError("FRED_API_KEY is not set in environment variables.")
    data_manager = DataManager(api_key=api_key)

    yield
    # 在應用關閉時執行的程式碼
    print("Bond Data Service is shutting down...")

app = FastAPI(
    lifespan=lifespan,
    title="Bond Data Service",
    description="一個專門用來獲取和提供債券相關宏觀經濟數據的微服務。",
    version="0.1.0",
)

# --- CORS (跨來源資源共用) 設定 ---
# 允許所有來源，在生產環境中應更嚴格
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ping")
async def ping():
    """健康檢查端點"""
    return {"status": "ok", "message": "Bond Data Service is running."}

@app.post("/fetch/{indicator}")
async def fetch_data_endpoint(indicator: str):
    """觸發特定指標的資料抓取與儲存"""
    try:
        print(f"收到 '{indicator}' 的資料抓取請求...")
        count = data_manager.fetch_and_store_data(indicator)
        return {"indicator": indicator, "message": f"成功抓取並儲存了 {count} 筆數據。"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"處理時發生內部錯誤: {e}")

@app.get("/data/{indicator}")
async def get_data_endpoint(indicator: str):
    """獲取指定指標的已儲存數據"""
    try:
        data = data_manager.get_data(indicator)
        if not data:
            # 即使沒有數據，也返回一個空的列表，讓前端更容易處理
            return []
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取數據時發生內部錯誤: {e}")
