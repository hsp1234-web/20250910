# services/bond_data_service/api_routes.py
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from .service import StressIndexService

# --- 依賴注入 ---
service: Optional[StressIndexService] = None

logger = logging.getLogger(__name__)
router = APIRouter()

# --- 輔助函式 ---
def _ensure_service() -> StressIndexService:
    """確保服務已被初始化。"""
    if service is None:
        raise HTTPException(status_code=503, detail="服務尚未完全初始化。")
    return service

# --- API 端點 ---
@router.get("/health", summary="服務健康狀態檢查")
async def health_check():
    """提供一個簡單、快速的健康檢查端點。"""
    return {"status": "ok", "message": "債券資料分析服務已就緒。"}

@router.get("/data/{chart_id}", summary="獲取圖表所需的 JSON 數據")
async def get_chart_data(
    chart_id: str,
    start_date: str = Query(..., description="數據開始日期 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="數據結束日期 (YYYY-MM-DD)")
):
    """
    為前端圖表提供統一的 JSON 數據源。
    此端點現在是非阻塞的。如果數據尚未快取，它會觸發背景抓取並返回 202 狀態。
    """
    svc = _ensure_service()
    try:
        logger.info(f"API 層：收到圖表 '{chart_id}' 的數據請求...")

        # 1. 呼叫異步服務層獲取數據和就緒狀態
        full_metrics_df, data_ready = await svc.calculate_full_metrics(start_date, end_date)

        # 2. 處理資料尚未就緒的情況
        if not data_ready:
            logger.info(f"為 '{chart_id}' 請求的數據正在背景抓取中。")
            return JSONResponse(
                status_code=202, # Accepted
                content={"status": "processing", "message": "數據正在準備中，請稍後重試。"}
            )

        # 3. 處理服務層返回空數據的情況（在資料就緒後）
        if full_metrics_df is None or full_metrics_df.empty:
            logger.warning(f"為 '{chart_id}' 請求的數據就緒，但結果為空。")
            return JSONResponse(content=[], status_code=200)

        # 4. 根據 chart_id 篩選並格式化數據 (與舊邏輯相同)
        required_cols = {
            "sofr": ['sofr', 'sofr_ma60'], "ofr_fci": ['dealer_stress_index'], "vix": ['vix'],
            "us_bond_2y_10y_spread": ['spread_10y2y'], "us_high_yield_spread": ['us_high_yield_spread'],
            "stress_index": ['dealer_stress_index'],
            "stress_index_macd": ['dealer_stress_index', 'macd_line', 'macd_signal_line', 'macd_hist'],
            "dealer_net_positions": ['dealer_net_positions'],
            "dealer_long_term_positions": ['dealer_long_term_positions'],
            "dealer_short_term_positions": ['dealer_short_term_positions'],
            "dealer_net_position_ranking": ['dealer_net_positions', 'dealer_long_term_positions', 'dealer_short_term_positions'],
            "dealer_position_change_ranking": ['dealer_net_positions', 'dealer_long_term_positions', 'dealer_short_term_positions'],
        }.get(chart_id, [chart_id])

        cols_to_use = [col for col in required_cols if col in full_metrics_df.columns]
        if not cols_to_use:
            return JSONResponse(content=[], status_code=200)

        df_serializable = full_metrics_df.reset_index().rename(columns={'index': 'date'})
        df_serializable['date'] = pd.to_datetime(df_serializable['date']).dt.strftime('%Y-%m-%d')

        final_cols = ['date'] + [col for col in cols_to_use if col in df_serializable.columns]
        chart_df = df_serializable[final_cols]

        json_payload = chart_df.replace({pd.NaT: None, np.nan: None}).to_dict(orient='records')

        logger.info(f"成功為 '{chart_id}' 生成 {len(json_payload)} 筆數據。")
        return JSONResponse(content=json_payload)

    except Exception as e:
        logger.error(f"為圖表 '{chart_id}' 生成數據時發生嚴重錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"處理圖表 '{chart_id}' 的請求時發生內部錯誤。")
