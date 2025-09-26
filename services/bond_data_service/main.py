# services/bond_data_service/main.py

import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import database
from data_manager import DataManager
import stress_index_calculator
import charting
import logging
import pandas as pd
import numpy as np
from typing import Optional

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

    default_api_key = "YOUR_DEFAULT_API_KEY"
    api_key = os.getenv("FRED_API_KEY", default_api_key)

    if api_key == default_api_key:
        logger.warning("未偵測到 FRED_API_KEY 環境變數，將使用預設的假金鑰。資料抓取功能將無法運作。")
    else:
        logger.info("成功讀取 FRED_API_KEY。")

    data_manager = DataManager(api_key=api_key)
    yield
    logger.info("Bond Data Service is shutting down...")

app = FastAPI(
    lifespan=lifespan,
    title="債券與一級交易商分析服務",
    description="一個提供債券相關宏觀經濟數據，並計算與呈現一級交易商壓力指數相關圖表的微服務。",
    version="1.2.0", # 版本升級
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

@app.get("/debug/all_metrics")
async def get_all_metrics_debug():
    """
    [除錯用] 獲取所有計算指標的原始 DataFrame 數據。
    注意：這會回傳大量數據，僅供開發和驗證使用。
    """
    try:
        logger.info("[除錯] 正在請求所有指標數據...")
        full_metrics_df = stress_index_calculator.calculate_full_metrics(data_manager)
        df_serializable = full_metrics_df.reset_index().replace({pd.NaT: None, np.nan: None})
        json_str = df_serializable.to_json(orient='records', date_format='iso')
        logger.info(f"[除錯] 成功生成指標數據，共 {len(df_serializable)} 筆。")
        return Response(content=json_str, media_type="application/json")
    except Exception as e:
        logger.error(f"[除錯] 生成所有指標數據時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成除錯數據時發生內部錯誤: {e}")

@app.get("/chart/{chart_id}")
async def get_unified_chart_endpoint(
    chart_id: str,
    start_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD 格式)"),
    end_date: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD 格式)")
):
    """
    統一的圖表生成端點。
    根據 chart_id 生成對應的圖表並以圖片格式返回。
    支援 `start_date` 和 `end_date` 查詢參數進行日期篩選。
    """
    global metrics_cache

    chart_dispatcher = {
        "sofr": charting.plot_sofr,
        "vix": charting.plot_vix,
        "stress_index": charting.plot_stress_index,
        "gauge": charting.plot_gauge,
        "trend": charting.plot_trend,
        "us_bond_2y_10y_spread": charting.plot_spread_10y2y,
        "spread_10y2y": charting.plot_spread_10y2y,
        "dealer_net_positions": charting.plot_dealer_positions,
        "dealer_positions": charting.plot_dealer_positions,
        "stress_index_macd": charting.plot_macd,
        "macd": charting.plot_macd,
        "ofr_fci": charting.plot_stress_index,
        "us_high_yield_spread": charting.plot_us_high_yield_spread,
        "dealer_short_term_positions": lambda df: charting.plot_dealer_positions_by_maturity(df, 'short'),
        "dealer_long_term_positions": lambda df: charting.plot_dealer_positions_by_maturity(df, 'long'),
        "dealer_net_position_ranking": lambda df: charting.plot_not_available("交易商淨部位排名"),
        "dealer_position_change_ranking": lambda df: charting.plot_not_available("交易商部位變動排名"),
        "reserves": charting.plot_reserves,
        "etf_tlt": charting.plot_etf_tlt,
        "pos_res_ratio": charting.plot_pos_res_ratio,
    }

    plot_function = chart_dispatcher.get(chart_id)

    try:
        logger.info(f"開始為圖表 '{chart_id}' 計算完整指標...")
        full_metrics_df = stress_index_calculator.calculate_full_metrics(data_manager)

        if full_metrics_df.empty:
            logger.error("指標計算結果為空，無法生成圖表。")
            fig = charting.plot_not_available(f"圖表 '{chart_id}' (指標計算失敗)")
            return Response(content=charting.generate_chart_response(fig), media_type="image/jpeg")

        # --- 日期篩選邏輯 ---
        df_to_plot = full_metrics_df
        if start_date or end_date:
            logger.info(f"收到日期篩選請求: 從 {start_date or '開始'} 到 {end_date or '結束'}")
            try:
                if not isinstance(df_to_plot.index, pd.DatetimeIndex):
                    df_to_plot.index = pd.to_datetime(df_to_plot.index)

                mask = pd.Series(True, index=df_to_plot.index)
                if start_date:
                    mask &= (df_to_plot.index >= pd.to_datetime(start_date))
                if end_date:
                    mask &= (df_to_plot.index <= pd.to_datetime(end_date))

                df_to_plot = df_to_plot[mask]
                logger.info(f"篩選後剩下 {len(df_to_plot)} 筆數據。")
            except Exception as date_exc:
                logger.error(f"解析日期範圍 '{start_date}' - '{end_date}' 時出錯: {date_exc}", exc_info=True)
                fig = charting.plot_not_available(f"圖表 '{chart_id}' (日期格式錯誤)")
                return Response(content=charting.generate_chart_response(fig), media_type="image/jpeg", status_code=400)

        if df_to_plot.empty:
            logger.warning(f"在指定日期範圍內無數據可供繪製圖表 '{chart_id}'。")
            fig = charting.plot_not_available(f"圖表 '{chart_id}' (範圍內無數據)")
            return Response(content=charting.generate_chart_response(fig), media_type="image/jpeg")

        if not plot_function:
            logger.warning(f"找不到 chart_id '{chart_id}' 的對應函式。")
            fig = charting.plot_not_available(f"圖表 '{chart_id}'")
            return Response(content=charting.generate_chart_response(fig), media_type="image/jpeg")

        logger.info(f"正在為 '{chart_id}' 調用繪圖函式...")
        fig = plot_function(df_to_plot)

        if fig is None:
            logger.warning(f"圖表 '{chart_id}' 因數據不足而無法生成。")
            fig = charting.plot_not_available(f"圖表 '{chart_id}' (數據不足)")
            return Response(content=charting.generate_chart_response(fig), media_type="image/jpeg")

        img_bytes = charting.generate_chart_response(fig)
        logger.info(f"圖表 '{chart_id}' 已成功生成並準備回傳。")
        return Response(content=img_bytes, media_type="image/jpeg")

    except Exception as e:
        logger.error(f"為 '{chart_id}' 生成圖表時發生未預期錯誤: {e}", exc_info=True)
        fig = charting.plot_not_available(f"圖表 '{chart_id}' (內部伺服器錯誤)")
        return Response(content=charting.generate_chart_response(fig), media_type="image/jpeg", status_code=500)