# poc/bond_data_service_v2/api_routes.py

import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, List
import asyncio
import json
from asyncio import Queue

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, JSONResponse, StreamingResponse, FileResponse

# 匯入新的服務層
from .service import StressIndexService

# --- 依賴注入 ---
# 這個 service 實例將在 main.py 的 lifespan 中被賦值。
# 這使得 API 層與服務層的具體實現解耦。
service: Optional[StressIndexService] = None

# --- API 層狀態 ---
# SSE 連線列表是純粹的 API 層狀態，應保留在此。
sse_connections: List[Queue] = []

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Server-Sent Events (SSE) ---

async def broadcast_update(data: dict):
    """將更新廣播給所有已連接的 SSE 客戶端。"""
    message = f"data: {json.dumps(data)}\n\n"
    logger.info(f"API 層：準備廣播更新，目前有 {len(sse_connections)} 個連線。")
    for queue in sse_connections:
        await queue.put(message)

async def sse_data_generator(request: Request):
    """為每個客戶端管理一個 SSE 連線和數據佇列。"""
    queue = Queue()
    sse_connections.append(queue)
    logger.info(f"新客戶端連接，目前共 {len(sse_connections)} 個連線。")
    try:
        while True:
            if await request.is_disconnected():
                break
            message = await queue.get()
            yield message
    finally:
        sse_connections.remove(queue)
        logger.info(f"一個連線關閉，剩餘 {len(sse_connections)} 個連線。")

# --- API 端點 (已重構為呼叫服務層) ---

def _ensure_service() -> StressIndexService:
    """確保服務已被初始化，並返回它。"""
    if service is None:
        # 這通常不應該發生，因為 lifespan 會先於請求處理
        raise HTTPException(status_code=503, detail="服務尚未完全初始化。")
    return service

@router.get("/health", summary="服務健康狀態檢查")
async def health_check():
    return {"status": "ok", "message": "債券資料服務 (v2) 已就緒。"}

@router.get("/api/key_status", summary="檢查 FRED API 金鑰狀態")
async def get_key_status():
    """檢查 FRED API 金鑰是否已透過環境變數設定。"""
    svc = _ensure_service()
    if svc.repository.check_api_key_status():
        return {"status": "ok", "message": "FRED API 金鑰已就緒。"}
    else:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "尚未設定 FRED API 金鑰。"}
        )

@router.post("/fetch/{indicator}", summary="手動觸發資料抓取")
async def fetch_data_endpoint(indicator: str):
    """手動觸發特定指標的資料抓取與儲存。"""
    svc = _ensure_service()
    try:
        count = svc.repository.get_series(indicator, "1900-01-01", datetime.now().strftime('%Y-%m-%d'), force_refresh=True)
        return {"indicator": indicator, "message": f"成功為 '{indicator}' 抓取並儲存了 {len(count) if count is not None else 0} 筆數據。"}
    except Exception as e:
        logger.error(f"API 層在處理抓取請求 '{indicator}' 時出錯: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"處理 '{indicator}' 時發生內部錯誤。")

@router.get("/api/bond_service/dashboard_data", summary="獲取儀表板整合數據")
async def get_dashboard_data(start_date: Optional[str] = None, end_date: Optional[str] = None):
    svc = _ensure_service()
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    if not start_date:
        start_date = (datetime.now() - pd.DateOffset(years=5)).strftime('%Y-%m-%d')

    full_metrics_df = svc.calculate_full_metrics(start_date, end_date)

    if full_metrics_df is None or full_metrics_df.empty:
        return []

    dashboard_cols = [
        'sofr', 'sofr_ma60', 'dealer_stress_index', 'macd_line', 'macd_signal_line',
        'macd_hist', 'vix', 'spread_10y2y', 'us_high_yield_spread',
        'dealer_net_positions', 'dealer_long_term_positions', 'dealer_short_term_positions'
    ]
    cols_to_use = [col for col in dashboard_cols if col in full_metrics_df.columns]

    chart_df = full_metrics_df[cols_to_use]
    df_serializable = chart_df.reset_index().replace({pd.NaT: None, np.nan: None})
    df_serializable['date'] = pd.to_datetime(df_serializable['date']).dt.strftime('%Y-%m-%d')
    return json.loads(df_serializable.to_json(orient='records'))

@router.get("/charts/stream-updates", summary="建立 SSE 連線以接收即時更新")
async def stream_updates(request: Request):
    return StreamingResponse(sse_data_generator(request), media_type="text/event-stream")

# 靜態頁面路由
@router.get("/primary_dealer_analysis", response_class=FileResponse, include_in_schema=False)
async def get_primary_dealer_analysis_page():
    # 依賴於一個相對於專案根目錄的固定路徑
    return "src/static/primary_dealer_analysis.html"

@router.get("/interactive_chart", response_class=FileResponse, include_in_schema=False)
async def get_interactive_chart_page():
    return "src/static/interactive_chart.html"