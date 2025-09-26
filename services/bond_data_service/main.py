# services/bond_data_service/main.py

import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from . import database
from .data_manager import DataManager
from . import stress_index_calculator
import plotly.graph_objects as go
import io

# --- Global instances ---
data_manager = None

# --- Constants ---
INDICATOR_LABELS = {
    "gdp": "US Real GDP (Billions of Dollars)",
    "cpi": "US CPI (Annual Rate)",
    "fedfunds": "Federal Funds Rate (%)",
    "ism": "US ISM Manufacturing PMI",
    "dealer_stress_index": "一級交易商壓力指數 (Primary Dealer Stress Index)"
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global data_manager
    # 在應用啟動時執行的程式碼
    print("Bond Data Service is starting up...")
    database.initialize_database()

    # 強制從環境變數讀取 API 金鑰
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        # 如果未設定環境變數，則服務啟動失敗
        raise ValueError("啟動失敗：請設定 FRED_API_KEY 環境變數。")
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

@app.get("/chart/dealer_stress_index")
async def get_stress_index_chart_endpoint():
    """
    計算一級交易商壓力指數，生成圖表並以圖片格式返回。
    """
    try:
        # 1. 計算壓力指數
        # data_manager 是在 lifespan 中初始化的全局變數
        if not data_manager:
            raise HTTPException(status_code=503, detail="DataManager is not initialized.")

        print("收到壓力指數圖表請求，開始計算...")
        stress_index_series = stress_index_calculator.calculate_stress_index(data_manager)

        # 2. 如果沒有數據，返回錯誤
        if stress_index_series is None or stress_index_series.empty:
            raise HTTPException(status_code=404, detail="無法計算壓力指數，可能基礎數據不足。")

        # 3. 準備繪圖數據
        dates = stress_index_series.index
        values = stress_index_series.values
        title = INDICATOR_LABELS.get("dealer_stress_index")

        # 4. 使用 Plotly 繪圖
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=values, mode='lines', name=title))
        fig.update_layout(
            title=title,
            xaxis_title="Date",
            yaxis_title="Index (0-100)",
            template="plotly_white",
            yaxis_range=[0,100] # 壓力指數範圍是 0-100
        )

        # 5. 將圖表轉換為圖片並存入記憶體
        img_bytes = fig.to_image(format="jpeg", width=800, height=500, scale=2)

        # 6. 回傳圖片
        print("壓力指數圖表生成成功，正在回傳圖片。")
        return Response(content=img_bytes, media_type="image/jpeg")

    except Exception as e:
        print(f"為 'dealer_stress_index' 生成圖表時發生錯誤: {e}")
        # 為了安全，不在 production 環境中暴露詳細錯誤
        raise HTTPException(status_code=500, detail=f"生成壓力指數圖表時發生內部錯誤。")

@app.get("/chart/{indicator_id}")
async def get_chart_endpoint(indicator_id: str):
    """
    獲取指定指標的數據，生成圖表並以圖片格式返回。
    """
    try:
        # 1. 獲取數據
        data = data_manager.get_data(indicator_id)

        # 2. 如果沒有數據，觸發抓取
        if not data:
            print(f"'{indicator_id}' 在資料庫中沒有數據，正在觸發自動抓取...")
            data_manager.fetch_and_store_data(indicator_id)
            data = data_manager.get_data(indicator_id)

            if not data:
                # 如果還是沒有數據，可以返回一個"無資料"的圖片或錯誤
                # 這裡我們選擇拋出錯誤，讓前端知道
                raise HTTPException(status_code=404, detail=f"指標 '{indicator_id}' 在嘗試更新後依然沒有數據。")

        # 3. 準備繪圖數據
        dates = [item['date'] for item in data]
        values = [item['value'] for item in data]
        title = INDICATOR_LABELS.get(indicator_id, indicator_id.upper())

        # 4. 使用 Plotly 繪圖
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=values, mode='lines', name=title))
        fig.update_layout(
            title=title,
            xaxis_title="Date",
            yaxis_title="Value",
            template="plotly_white"
        )

        # 5. 將圖表轉換為圖片並存入記憶體
        img_bytes = fig.to_image(format="jpeg", width=800, height=500, scale=2)

        # 6. 回傳圖片
        return Response(content=img_bytes, media_type="image/jpeg")

    except ValueError as e:
        # 這是 data_manager.fetch_and_store_data 可能拋出的錯誤
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"為 '{indicator_id}' 生成圖表時發生錯誤: {e}")
        # 為了安全，不在 production 環境中暴露詳細錯誤
        raise HTTPException(status_code=500, detail=f"生成圖表時發生內部錯誤。")
