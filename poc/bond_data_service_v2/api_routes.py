# poc/bond_data_service_v2/api_routes.py
# 繁體中文註解：API 路由模組 (已修正導入問題)

import asyncio
import json
import logging
from asyncio import Queue
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd
from fastapi import (APIRouter, HTTPException, Query, Request)
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

# 導入整個 globals 模組，以確保總是能獲取到最新的實例
from . import globals

logger = logging.getLogger(__name__)
router = APIRouter()


# --- 靜態檔案與頁面路由 ---
@router.get("/primary_dealer_analysis", response_class=FileResponse, include_in_schema=False)
async def get_primary_dealer_analysis_page():
    return globals.HTML_DIR / "primary_dealer_analysis.html"

@router.get("/interactive_chart", response_class=FileResponse, include_in_schema=False)
async def get_interactive_chart_page():
    return globals.HTML_DIR / "interactive_chart.html"


# --- API 端點 ---
@router.get("/health", summary="服務健康狀態檢查")
async def health_check():
    return JSONResponse(content={"status": "ok", "message": "債券資料服務已就緒。"})

@router.get("/api/key_status", summary="檢查 FRED API 金鑰的狀態")
async def get_key_status():
    if globals.data_repository and globals.data_repository.check_api_key_status():
        return JSONResponse(status_code=200, content={"status": "ok", "message": "FRED API 金鑰已就緒。"})
    else:
        return JSONResponse(status_code=404, content={"status": "error", "message": "尚未設定或找不到 FRED API 金鑰。"})

@router.post("/fetch/{indicator}", summary="手動觸發資料強制刷新")
async def fetch_data_endpoint(indicator: str):
    try:
        logger.info(f"收到對 '{indicator}' 的手動強制刷新請求...")
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - pd.DateOffset(years=30)).strftime('%Y-%m-%d')
        series = globals.data_repository.get_series(indicator, start_date, end_date, force_refresh=True)
        count = len(series) if series is not None else 0
        return {"indicator": indicator, "message": f"成功為 '{indicator}' 強制刷新並儲存了 {count} 筆數據。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/bond_service/dashboard_data", summary="獲取儀表板所需的所有整合數據")
async def get_dashboard_data(
    start_date: Optional[str] = Query(None, description="數據開始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="數據結束日期 (YYYY-MM-DD)")
):
    try:
        if not end_date: end_date = datetime.now().strftime('%Y-%m-%d')
        if not start_date: start_date = (datetime.now() - pd.DateOffset(years=5)).strftime('%Y-%m-%d')

        logger.info(f"API 層：正在請求儀表板數據，範圍: {start_date} 至 {end_date}...")
        full_metrics_df = globals.stress_index_service.calculate_full_metrics(start_date, end_date)

        if full_metrics_df is None or full_metrics_df.empty:
            return JSONResponse(content=[])

        dashboard_cols = [
            'sofr', 'sofr_ma60', 'dealer_stress_index', 'macd_line', 'macd_signal_line',
            'macd_hist', 'vix', 'spread_10y2y', 'us_high_yield_spread',
            'dealer_net_positions', 'dealer_long_term_positions', 'dealer_short_term_positions'
        ]
        cols_to_use = [col for col in dashboard_cols if col in full_metrics_df.columns]
        if not cols_to_use: raise HTTPException(status_code=500, detail="指標計算未能生成儀表板所需數據。")

        chart_df = full_metrics_df[cols_to_use]
        df_serializable = chart_df.reset_index().replace({pd.NaT: None, np.nan: None})
        df_serializable = df_serializable.rename(columns={'index': 'date'})
        df_serializable['date'] = df_serializable['date'].dt.strftime('%Y-%m-%d')
        json_payload = df_serializable.to_dict(orient='records')
        return JSONResponse(content=json_payload)
    except Exception as e:
        logger.error(f"生成整合儀表板數據時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"處理儀表板數據請求時發生內部錯誤: {e}")

# --- SSE 相關功能 ---
async def broadcast_update(data: dict):
    message = f"data: {json.dumps(data)}\n\n"
    for queue in globals.sse_connections:
        await queue.put(message)

async def sse_data_generator(request: Request):
    queue = Queue()
    globals.sse_connections.append(queue)
    try:
        while True:
            if await request.is_disconnected(): break
            message = await queue.get()
            yield message
    finally:
        globals.sse_connections.remove(queue)

@router.get("/charts/stream-updates", summary="建立一個 SSE 連線以接收即時更新")
async def stream_updates(request: Request):
    return StreamingResponse(sse_data_generator(request), media_type="text/event-stream")