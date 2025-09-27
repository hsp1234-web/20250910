# services/bond_data_service/main.py

import os
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import database
from data_manager import DataManager
import stress_index_calculator
import charting
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, List
import asyncio
import json
from asyncio import Queue

# --- Global instances ---
data_manager = None
# 新增一個快取，用於儲存計算好的完整指標，避免重複計算
metrics_cache = {"data": None, "timestamp": None}
# 用於管理所有活躍的 SSE 連線
sse_connections = []

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Background Task for Live Updates ---
last_broadcasted_timestamp = None

async def periodic_data_updater():
    """
    定期在背景檢查是否有新的數據點，並透過 SSE 廣播。
    """
    global last_broadcasted_timestamp
    await asyncio.sleep(15) # 啟動後延遲一下，等待服務完全就緒

    while True:
        try:
            logger.info("背景更新任務：開始檢查新數據...")
            # 為了效率，我們只計算最近一段時間的數據
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - pd.DateOffset(days=30)).strftime('%Y-%m-%d')

            full_metrics_df = stress_index_calculator.calculate_full_metrics(data_manager, start_date, end_date)

            if full_metrics_df is not None and not full_metrics_df.empty:
                # 取得最新的有效數據點，並確保在操作前它不為空
                valid_data = full_metrics_df.dropna(subset=['dealer_stress_index'])
                if not valid_data.empty:
                    latest_data_point = valid_data.iloc[-1]
                    latest_timestamp = latest_data_point.name # The index (date) is the name of the series row

                    if last_broadcasted_timestamp is None or latest_timestamp > last_broadcasted_timestamp:
                        logger.info(f"偵測到新數據點 (時間戳: {latest_timestamp})，準備廣播...")

                        # 準備廣播的 JSON payload
                        payload = {
                            'date': latest_timestamp.isoformat(),
                            'dealer_stress_index': latest_data_point.get('dealer_stress_index'),
                            'macd_line': latest_data_point.get('macd_line'),
                            'macd_signal_line': latest_data_point.get('macd_signal_line'),
                            'macd_hist': latest_data_point.get('macd_hist')
                        }
                        # 清理掉 NaN 值，轉換為 None
                        payload_clean = {k: (None if pd.isna(v) else v) for k, v in payload.items()}

                        await broadcast_update(payload_clean)
                        last_broadcasted_timestamp = latest_timestamp
                    else:
                        logger.info(f"背景更新任務：無新數據點。上次更新時間: {last_broadcasted_timestamp}")
                else:
                    logger.info("背景更新任務：計算後無有效的壓力指數數據點可廣播。")
            else:
                logger.warning("背景更新任務：計算指標未返回有效數據。")

        except Exception as e:
            logger.error(f"背景數據更新任務發生錯誤: {e}", exc_info=True)

        # 等待下一次檢查，例如 5 分鐘
        await asyncio.sleep(300)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global data_manager
    logger.info("債券資料服務啟動中...")
    database.initialize_database()

    default_api_key = "YOUR_DEFAULT_API_KEY"
    api_key = os.getenv("FRED_API_KEY", default_api_key)

    if api_key == default_api_key:
        logger.warning("未偵測到 FRED_API_KEY 環境變數，將使用預設的假金鑰。資料抓取功能將無法運作。")
    else:
        logger.info("成功讀取 FRED_API_KEY。")

    data_manager = DataManager(api_key=api_key)

    # 啟動背景更新任務
    update_task = asyncio.create_task(periodic_data_updater())

    yield

    # 應用程式關閉時，優雅地取消背景任務
    logger.info("正在關閉背景更新任務...")
    update_task.cancel()
    try:
        await update_task
    except asyncio.CancelledError:
        logger.info("背景更新任務已成功取消。")

    logger.info("債券資料服務已關閉。")

app = FastAPI(
    lifespan=lifespan,
    title="債券與一級交易商分析服務",
    description="一個提供債券相關宏觀經濟數據，並計算與呈現一級交易商壓力指數相關圖表的微服務。",
    version="1.2.0",
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

@app.get("/ping", summary="服務健康檢查")
async def ping():
    """
    執行一個快速的健康檢查。
    如果服務正常運行，會返回一個成功的訊息。
    """
    return {"status": "ok", "message": "債券資料服務運行中。"}

@app.post("/fetch/{indicator}", summary="手動觸發資料抓取")
async def fetch_data_endpoint(indicator: str):
    """手動觸發特定基礎指標的資料抓取與儲存"""
    try:
        logger.info(f"收到對 '{indicator}' 的手動資料抓取請求...")
        count = data_manager.fetch_and_store_data(indicator)
        return {"indicator": indicator, "message": f"成功為 '{indicator}' 抓取並儲存了 {count} 筆數據。"}
    except ValueError as e:
        logger.error(f"找不到指標 '{indicator}' 的抓取器: {e}")
        raise HTTPException(status_code=404, detail=f"找不到指標 '{indicator}' 的抓取器。")
    except Exception as e:
        logger.error(f"處理抓取請求 '{indicator}' 時發生內部錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"處理 '{indicator}' 時發生內部錯誤: {e}")

@app.get("/debug/all_metrics")
async def get_all_metrics_debug():
    """
    [除錯用] 獲取所有計算指標的原始 DataFrame 數據。
    注意：這會回傳大量數據，僅供開發和驗證使用。
    """
    try:
        logger.info("[除錯] 正在請求所有指標數據...")
        # 設定一個預設的廣泛日期範圍
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - pd.DateOffset(years=20)).strftime('%Y-%m-%d')
        full_metrics_df = stress_index_calculator.calculate_full_metrics(data_manager, start_date, end_date)

        if full_metrics_df is None:
            raise HTTPException(status_code=500, detail="計算指標時返回了 None。")

        # 將 NaN 轉換為 None (JSON 可序列化) 並重置索引，使日期成為一欄
        df_serializable = full_metrics_df.reset_index().replace({pd.NaT: None, np.nan: None})
        df_serializable = df_serializable.rename(columns={'index': 'date'})

        # 轉換為 JSON 字串，處理日期格式
        json_str = df_serializable.to_json(orient='records', date_format='iso')

        logger.info(f"[除錯] 成功生成指標數據，共 {len(df_serializable)} 筆。")
        return Response(content=json_str, media_type="application/json")

    except Exception as e:
        logger.error(f"[除錯] 生成所有指標數據時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成除錯數據時發生內部錯誤: {e}")


@app.get("/charts/stress-index", summary="獲取壓力指數圖表數據")
async def get_stress_index_data(
    start_date: Optional[str] = Query(None, description="數據開始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="數據結束日期 (YYYY-MM-DD)")
):
    """
    為前端提供繪製「一級交易商壓力指數」圖表所需的完整歷史數據。
    """
    try:
        # 如果未提供日期，則設定預設範圍（過去五年）
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if not start_date:
            start_date = (datetime.now() - pd.DateOffset(years=5)).strftime('%Y-%m-%d')

        logger.info(f"正在為壓力指數圖表計算指標，範圍: {start_date} 至 {end_date}...")
        full_metrics_df = stress_index_calculator.calculate_full_metrics(data_manager, start_date, end_date)

        if full_metrics_df is None or full_metrics_df.empty:
            logger.error("指標計算結果為空，無法提供圖表數據。")
            raise HTTPException(status_code=404, detail="在指定範圍內無足夠數據可生成圖表。")

        # 篩選前端需要的欄位
        chart_data_cols = [
            'dealer_stress_index',
            'macd_line',
            'macd_signal_line',
            'macd_hist'
        ]
        # 確保所有需要的欄位都存在
        cols_to_use = [col for col in chart_data_cols if col in full_metrics_df.columns]

        if not cols_to_use:
            logger.error("計算結果中不包含任何繪圖所需的核心指標欄位。")
            raise HTTPException(status_code=500, detail="指標計算未能生成必要數據。")

        chart_df = full_metrics_df[cols_to_use]

        # 將 NaN 轉換為 None (JSON 可序列化) 並重置索引，使日期成為一欄
        df_serializable = chart_df.reset_index().replace({pd.NaT: None, np.nan: None})
        df_serializable = df_serializable.rename(columns={'index': 'date'})

        # 轉換為 JSON 格式
        json_payload = df_serializable.to_dict(orient='records')

        logger.info(f"成功生成壓力指數圖表數據，共 {len(json_payload)} 筆。")
        return JSONResponse(content=json_payload)

    except Exception as e:
        logger.error(f"生成壓力指數圖表數據時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"處理請求時發生內部錯誤: {e}")


# --- Server-Sent Events (SSE) 相關功能 ---

async def broadcast_update(data: dict):
    """
    將更新廣播給所有已連接的 SSE 客戶端。
    """
    # 格式化為 SSE 訊息
    message = f"data: {json.dumps(data)}\n\n"
    logger.info(f"準備廣播更新，目前有 {len(sse_connections)} 個連線。")
    # 將訊息放入每個客戶端的佇列中
    for queue in sse_connections:
        try:
            await queue.put(message)
        except Exception as e:
            logger.error(f"放入佇列時出錯: {e}")


async def sse_data_generator(request: Request):
    """
    為每個客戶端管理一個 SSE 連線和數據佇列。
    """
    queue = Queue()
    sse_connections.append(queue)
    logger.info(f"新客戶端已連接，目前共 {len(sse_connections)} 個連線。")
    try:
        while True:
            # 檢查客戶端是否已斷開連接
            if await request.is_disconnected():
                logger.info("客戶端已斷開連接。")
                break
            # 從佇列等待新訊息
            message = await queue.get()
            yield message
    except asyncio.CancelledError:
        logger.info("生成器被取消，客戶端可能已關閉。")
    finally:
        # 從連線列表中移除該客戶端的佇列
        sse_connections.remove(queue)
        logger.info(f"一個連線已關閉，剩餘 {len(sse_connections)} 個連線。")


@app.get("/charts/stream-updates", summary="建立一個 SSE 連線以接收即時更新")
async def stream_updates(request: Request):
    """
    此端點會建立一個伺服器發送事件 (SSE) 連線。
    當後端有新的金融數據點時，會即時推送到此連線。
    """
    return StreamingResponse(sse_data_generator(request), media_type="text/event-stream")


@app.post("/broadcast-update", summary="[測試用] 手動廣播一條更新")
async def trigger_broadcast(message: dict):
    """
    一個用於開發和測試的端點，可以手動觸發一次 SSE 廣播。
    請求主體應該是一個 JSON 物件。
    範例: `{"date": "2024-10-27T12:00:00Z", "dealer_stress_index": 88.8}`
    """
    logger.info(f"收到手動廣播請求: {message}")
    await broadcast_update(message)
    return {"status": "ok", "message": f"已向 {len(sse_connections)} 個客戶端廣播更新。"}


@app.get("/chart/{chart_id}")
async def get_unified_chart_endpoint(
    chart_id: str,
    start_date: Optional[str] = Query(None, description="圖表數據的開始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="圖表數據的結束日期 (YYYY-MM-DD)")
):
    """
    統一的圖表生成端點。
    根據 chart_id 生成對應的圖表並以圖片格式返回。
    支援可選的日期範圍篩選。
    """
    global metrics_cache

    # 擴充後的圖表ID與繪圖函式的分派字典
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
        "dealer_net_position_ranking": charting.plot_dealer_net_position_ranking,
        "dealer_position_change_ranking": charting.plot_dealer_position_change_ranking,
        "reserves": charting.plot_reserves,
        "etf_tlt": charting.plot_etf_tlt,
        "pos_res_ratio": charting.plot_pos_res_ratio,
    }

    plot_function = chart_dispatcher.get(chart_id)

    try:
        logger.info(f"開始為圖表 '{chart_id}' 計算完整指標...")
        # 確保傳遞日期參數給更新後的函式
        effective_start_date = start_date or (datetime.now() - pd.DateOffset(years=5)).strftime('%Y-%m-%d')
        effective_end_date = end_date or datetime.now().strftime('%Y-%m-%d')
        full_metrics_df = stress_index_calculator.calculate_full_metrics(data_manager, effective_start_date, effective_end_date)

        if full_metrics_df is None or full_metrics_df.empty:
            logger.error("指標計算結果為空，無法生成圖表。")
            fig = charting.plot_not_available(f"圖表 '{chart_id}' (指標計算失敗)")
            return Response(content=charting.generate_chart_response(fig), media_type="image/jpeg")

        # --- 日期篩選邏輯 ---
        filtered_df = full_metrics_df
        if start_date or end_date:
            try:
                start_dt = pd.to_datetime(start_date) if start_date else None
                end_dt = pd.to_datetime(end_date) if end_date else None

                if start_dt:
                    filtered_df = filtered_df[filtered_df.index >= start_dt]
                if end_dt:
                    filtered_df = filtered_df[filtered_df.index <= end_dt]

                logger.info(f"數據已篩選，範圍: {start_date} 至 {end_date}。剩餘 {len(filtered_df)} 行。")

                if filtered_df.empty:
                    logger.warning(f"在指定日期範圍內沒有圖表 '{chart_id}' 的數據。")
                    fig = charting.plot_not_available(f"圖表 '{chart_id}' (範圍內無數據)")
                    return Response(content=charting.generate_chart_response(fig), media_type="image/jpeg")
            except Exception as e:
                logger.error(f"無效的日期格式或篩選錯誤: {e}")
                fig = charting.plot_not_available(f"圖表 '{chart_id}' (日期格式無效)")
                return Response(content=charting.generate_chart_response(fig), media_type="image/jpeg", status_code=400)

        if not plot_function:
            logger.warning(f"找不到 chart_id '{chart_id}' 的對應函式。")
            fig = charting.plot_not_available(f"圖表 '{chart_id}'")
            return Response(content=charting.generate_chart_response(fig), media_type="image/jpeg")

        logger.info(f"正在為 '{chart_id}' 調用繪圖函式...")
        fig = plot_function(filtered_df)

        if fig is None:
            logger.warning(f"圖表 '{chart_id}' 因數據不足而無法生成。")
            fig = charting.plot_not_available(f"圖表 '{chart_id}' (數據不足)")
            return Response(content=charting.generate_chart_response(fig), media_type="image/jpeg")

        img_bytes = charting.generate_chart_response(fig)
        logger.info(f"圖表 '{chart_id}' 已成功生成並準備回傳。")
        return Response(content=img_bytes, media_type="image/jpeg")

    except Exception as e:
        logger.error(f"為 '{chart_id}' 生成圖表時發生未預期錯誤: {e}", exc_info=True)
        fig = charting.plot_not_available(f"圖表 '{chart_id}' (內部錯誤)")
        return Response(content=charting.generate_chart_response(fig), media_type="image/jpeg", status_code=500)