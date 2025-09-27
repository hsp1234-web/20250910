# services/bond_data_service/main.py

import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

# 匯入重構後的模組
from .database import initialize_database
from .data_manager import DataManager
from .stress_index_calculator import calculate_full_metrics

# --- 全域實例 ---
data_manager: Optional[DataManager] = None

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 專案路徑設定 ---
# .../services/bond_data_service/main.py -> .../src
SRC_PATH = Path(__file__).resolve().parent.parent.parent / 'src'
STATIC_PATH = SRC_PATH / 'static'


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理"""
    global data_manager
    logger.info("債券資料服務啟動中...")
    initialize_database()

    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        logger.warning("未偵測到 FRED_API_KEY 環境變數。部分 FRED 數據抓取功能可能無法運作。")
    else:
        logger.info("成功讀取 FRED_API_KEY。")

    data_manager = DataManager(api_key=api_key)
    yield
    logger.info("債券資料服務已關閉。")

app = FastAPI(
    lifespan=lifespan,
    title="債券與一級交易商分析服務 API",
    description="一個提供債券相關宏觀經濟數據，並計算壓力指數的 API 服務。",
    version="2.0.0",
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

@app.get("/ping", summary="服務健康檢查", tags=["系統"])
async def ping():
    """
    執行一個快速的健康檢查。
    如果服務正常運行，會返回一個成功的訊息。
    """
    return {"status": "ok", "message": "債券資料服務運行中。"}

@app.get("/api/chart_data/{indicator_id}", summary="獲取格式化後的圖表數據 (JSON)", tags=["圖表數據"])
async def get_chart_data(
    indicator_id: str,
    start_date: str = Query("2018-01-01", description="開始日期 (YYYY-MM-DD)"),
    end_date: str = Query(datetime.now().strftime('%Y-%m-%d'), description="結束日期 (YYYY-MM-DD)")
):
    """
    為指定指標提供用於前端圖表渲染的 JSON 數據。
    """
    if data_manager is None:
        raise HTTPException(status_code=503, detail="服務尚未完全初始化，請稍後再試。")

    logger.info(f"收到對 '{indicator_id}' 的圖表數據請求 ({start_date} to {end_date})。")

    try:
        full_metrics_df = calculate_full_metrics(data_manager, start_date, end_date)

        if full_metrics_df is None or full_metrics_df.empty:
            raise HTTPException(status_code=404, detail=f"無法為指標 '{indicator_id}' 在指定日期範圍內計算或獲取數據。")

        labels = full_metrics_df.index.strftime('%Y-%m-%d').tolist()
        datasets: List[Dict[str, Any]] = []

        # 根據指標ID，準備對應的數據集
        if indicator_id == 'sofr':
            datasets.append({'label': 'SOFR', 'data': full_metrics_df['sofr'].where(pd.notna(full_metrics_df['sofr']), None).tolist()})
            datasets.append({'label': 'SOFR 60日移動平均', 'data': full_metrics_df['sofr_ma60'].where(pd.notna(full_metrics_df['sofr_ma60']), None).tolist()})
        elif indicator_id == 'vix':
            datasets.append({'label': 'VIX 恐慌指數', 'data': full_metrics_df['vix'].where(pd.notna(full_metrics_df['vix']), None).tolist()})
        elif indicator_id == 'us_bond_2y_10y_spread':
            data_bps = (full_metrics_df['spread_10y2y'] * 100).where(pd.notna(full_metrics_df['spread_10y2y']), None)
            datasets.append({'label': '美債2年與10年利差 (BPS)', 'data': data_bps.tolist()})
        elif indicator_id == 'us_high_yield_spread':
            datasets.append({'label': '高收益債ETF (HYG) 價格', 'data': full_metrics_df['us_high_yield_spread'].where(pd.notna(full_metrics_df['us_high_yield_spread']), None).tolist()})
        elif indicator_id == 'stress_index':
            datasets.append({'label': '綜合壓力指數', 'data': full_metrics_df['dealer_stress_index'].where(pd.notna(full_metrics_df['dealer_stress_index']), None).tolist()})
        elif indicator_id == 'dealer_net_positions':
            data_bil = (full_metrics_df['dealer_net_positions'] / 1000).where(pd.notna(full_metrics_df['dealer_net_positions']), None)
            datasets.append({'label': '淨部位 (十億美元)', 'data': data_bil.tolist()})
        elif indicator_id == 'dealer_long_term_positions':
            data_bil = (full_metrics_df['dealer_long_term_positions'] / 1000).where(pd.notna(full_metrics_df['dealer_long_term_positions']), None)
            datasets.append({'label': '長天期淨部位 (十億美元)', 'data': data_bil.tolist()})
        elif indicator_id == 'dealer_short_term_positions':
            data_bil = (full_metrics_df['dealer_short_term_positions'] / 1000).where(pd.notna(full_metrics_df['dealer_short_term_positions']), None)
            datasets.append({'label': '短天期淨部位 (十億美元)', 'data': data_bil.tolist()})
        elif indicator_id == 'stress_index_macd':
            datasets.append({'label': '壓力指數 MACD', 'data': full_metrics_df['macd_hist'].where(pd.notna(full_metrics_df['macd_hist']), None).tolist(), 'type': 'bar'})
        else:
            logger.warning(f"指標 '{indicator_id}' 的數據準備邏輯尚未定義。")
            raise HTTPException(status_code=404, detail=f"指標 '{indicator_id}' 的數據準備邏輯尚未定義。")

        if not any(d['data'] for d in datasets) or all(all(x is None for x in d['data']) for d in datasets):
            logger.warning(f"為指標 '{indicator_id}' 生成的數據集為空。")

        return JSONResponse(content={"labels": labels, "datasets": datasets})

    except Exception as e:
        logger.error(f"為 '{indicator_id}' 獲取圖表數據時發生未預期錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"處理對 '{indicator_id}' 的請求時發生內部伺服器錯誤。")

# --- 掛載靜態檔案 ---
# 這會將 'src/static' 目錄下的所有檔案掛載到 '/static' 路徑
app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")

@app.get("/", include_in_schema=False)
async def root():
    """提供主儀表板頁面"""
    return FileResponse(str(STATIC_PATH / 'primary_dealer_analysis.html'))