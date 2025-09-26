# services/bond_data_service/main.py

import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import database
from data_manager import DataManager
import stress_index_calculator
import charting
import logging

# --- Global instances ---
data_manager = None
# 新增一個快取，用於儲存計算好的完整指標，避免重複計算
metrics_cache = {"data": None, "timestamp": None}

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global data_manager
    logger.info("Bond Data Service is starting up...")
    database.initialize_database()

    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        logger.critical("啟動失敗：請設定 FRED_API_KEY 環境變數。")
        raise ValueError("啟動失敗：請設定 FRED_API_KEY 環境變數。")

    data_manager = DataManager(api_key=api_key)
    yield
    logger.info("Bond Data Service is shutting down...")

app = FastAPI(
    lifespan=lifespan,
    title="債券與一級交易商分析服務",
    description="一個提供債券相關宏觀經濟數據，並計算與呈現一級交易商壓力指數相關圖表的微服務。",
    version="1.0.0",
)

# --- CORS 設定 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API 端點 ---

@app.get("/ping")
async def ping():
    """健康檢查端點"""
    return {"status": "ok", "message": "Bond Data Service is running."}

@app.post("/fetch/{indicator}")
async def fetch_data_endpoint(indicator: str):
    """手動觸發特定基礎指標的資料抓取與儲存"""
    try:
        logger.info(f"收到 '{indicator}' 的手動資料抓取請求...")
        count = data_manager.fetch_and_store_data(indicator)
        return {"indicator": indicator, "message": f"成功抓取並儲存了 {count} 筆數據。"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"處理抓取請求時發生內部錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"處理時發生內部錯誤: {e}")

@app.get("/chart/{chart_id}")
async def get_unified_chart_endpoint(chart_id: str):
    """
    統一的圖表生成端點。
    根據 chart_id 生成對應的圖表並以圖片格式返回。
    """
    global metrics_cache

    # 圖表ID與繪圖函式的分派字典
    chart_dispatcher = {
        "sofr": charting.plot_sofr,
        "spread_10y2y": charting.plot_spread_10y2y,
        "move_index": charting.plot_move_index,
        "vix": charting.plot_vix,
        "dealer_positions": charting.plot_dealer_positions,
        "reserves": charting.plot_reserves,
        "etf_tlt": charting.plot_etf_tlt,
        "pos_res_ratio": charting.plot_pos_res_ratio,
        "stress_index": charting.plot_stress_index,
        "macd": charting.plot_macd,
        "gauge": charting.plot_gauge,
        "trend": charting.plot_trend,
    }

    plot_function = chart_dispatcher.get(chart_id)
    if not plot_function:
        raise HTTPException(status_code=404, detail=f"找不到ID為 '{chart_id}' 的圖表。")

    try:
        # 步驟 1: 獲取完整的指標數據 (使用快取)
        # 這裡可以加入快取邏輯，例如5分鐘內不再重新計算
        # 為了POC，我們先簡單實現
        logger.info("開始為圖表請求計算完整指標...")
        full_metrics_df = stress_index_calculator.calculate_full_metrics(data_manager)

        if full_metrics_df.empty:
            logger.error("指標計算結果為空，無法生成圖表。")
            raise HTTPException(status_code=404, detail="計算指標失敗，可能基礎數據不足。")

        # 步驟 2: 呼叫對應的繪圖函式
        logger.info(f"正在為 '{chart_id}' 調用繪圖函式...")
        fig = plot_function(full_metrics_df)

        if fig is None:
            logger.warning(f"圖表 '{chart_id}' 因數據不足而無法生成。")
            raise HTTPException(status_code=404, detail=f"圖表 '{chart_id}' 因數據不足而無法生成。")

        # 步驟 3: 將圖表轉換為圖片並回傳
        img_bytes = charting.generate_chart_response(fig)
        logger.info(f"圖表 '{chart_id}' 已成功生成並準備回傳。")
        return Response(content=img_bytes, media_type="image/jpeg")

    except HTTPException as http_exc:
        # 重新拋出已知的 HTTP 錯誤
        raise http_exc
    except Exception as e:
        logger.error(f"為 '{chart_id}' 生成圖表時發生未預期錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成圖表 '{chart_id}' 時發生內部錯誤。")