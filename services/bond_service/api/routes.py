# -*- coding: utf-8 -*-
"""
API 路由 (Endpoints)

功能：
- 定義所有對外開放的 API 端點。
- 處理傳入的請求，並觸發背景分析任務。
- 從資料庫讀取分析結果並返回給客戶端。
"""
import logging
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

# 導入 Pydantic 模型用於資料驗證
from pydantic import BaseModel, Field
from datetime import datetime as dt

# 導入本服務的內部模組
from ..db import crud, models
from ..db.database import SessionLocal, engine
from ..core import data_fetcher, stress_calculator
from ..utils import plotting, reporting

# --- Pydantic 模型定義 ---

class AnalysisRequest(BaseModel):
    """請求模型：發起一次新的分析"""
    start_date: str = Field(..., example="2022-01-01", description="分析開始日期 (YYYY-MM-DD)")
    end_date: str = Field(..., example="2023-01-01", description="分析結束日期 (YYYY-MM-DD)")

class AnalysisTaskResponse(BaseModel):
    """回應模型：成功發起分析任務後返回"""
    task_id: int
    status: str
    message: str

class AnalysisResultResponse(BaseModel):
    """回應模型：查詢分析任務的完整結果"""
    id: int
    status: str
    created_at: dt
    start_date: str
    end_date: str
    stress_index_value: Optional[float] = None
    text_report: Optional[str] = None
    main_plot_base64: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        orm_mode = True # 允許從 ORM 模型直接轉換

# --- API Router ---

router = APIRouter()
logger = logging.getLogger(__name__)

# --- 資料庫依賴注入 ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 背景分析任務 ---
def run_full_analysis(analysis_id: int, db: Session):
    """
    這是在背景執行的主分析函式。
    """
    logger.info(f"背景任務開始：處理 analysis_id={analysis_id}")
    try:
        # 獲取任務參數
        task = crud.get_analysis(db, analysis_id)
        if not task:
            logger.error(f"背景任務失敗：找不到 analysis_id={analysis_id} 的紀錄。")
            return

        # 步驟 1: 獲取並合併數據
        logger.info(f"[{analysis_id}] 步驟 1: 獲取數據...")
        merged_df = data_fetcher.get_merged_data(task.start_date, task.end_date)

        # 步驟 2: 計算壓力指數
        logger.info(f"[{analysis_id}] 步驟 2: 計算指標...")
        final_df = stress_calculator.calculate_stress_index(merged_df)

        if final_df.empty or 'Dealer_Stress_Index' not in final_df.columns or final_df['Dealer_Stress_Index'].isna().all():
            raise ValueError("計算後未能產生有效的壓力指數數據。")

        # 步驟 3: 生成報告和圖表
        logger.info(f"[{analysis_id}] 步驟 3: 生成報告與圖表...")
        text_report = reporting.generate_text_report(final_df)
        # 簡化 PoC，只生成主圖表
        main_plot = plotting.plot_results_as_base64(final_df)

        # 步驟 4: 準備並儲存結果
        latest_stress_value = final_df['Dealer_Stress_Index'].dropna().iloc[-1] if not final_df['Dealer_Stress_Index'].dropna().empty else None

        results_payload = {
            "stress_index_value": latest_stress_value,
            "text_report": text_report,
            "main_plot_base64": main_plot,
        }

        logger.info(f"[{analysis_id}] 步驟 4: 更新資料庫為成功狀態...")
        crud.update_analysis_success(db, analysis_id, results_payload)
        logger.info(f"背景任務成功完成：analysis_id={analysis_id}")

    except Exception as e:
        error_message = f"分析時發生錯誤: {e}"
        logger.error(f"背景任務失敗 (analysis_id={analysis_id}): {error_message}", exc_info=True)
        # 更新資料庫為失敗狀態
        crud.update_analysis_failure(db, analysis_id, error_message)


# --- API 端點定義 ---

@router.post("/analysis", response_model=AnalysisTaskResponse, status_code=202)
def create_new_analysis(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    發起一個新的壓力指數分析任務。

    此端點會立即返回一個任務 ID，並在背景開始執行耗時的分析流程。
    """
    logger.info(f"收到新的分析請求: {request.start_date} 到 {request.end_date}")
    # 1. 在資料庫中建立一個新的任務紀錄
    db_analysis = crud.create_analysis(db, start_date=request.start_date, end_date=request.end_date)

    # 2. 將主分析函式加入背景任務佇列
    background_tasks.add_task(run_full_analysis, db_analysis.id, db)

    return {
        "task_id": db_analysis.id,
        "status": "PENDING",
        "message": "分析任務已成功排入佇列，請稍後使用 GET /analysis/{task_id} 查詢結果。"
    }

@router.get("/analysis/{analysis_id}", response_model=AnalysisResultResponse)
def get_analysis_result(analysis_id: int, db: Session = Depends(get_db)):
    """
    根據任務 ID 查詢分析結果。
    """
    logger.info(f"查詢分析結果，task_id={analysis_id}")
    db_analysis = crud.get_analysis(db, analysis_id)
    if db_analysis is None:
        raise HTTPException(status_code=404, detail="找不到指定的分析任務 ID。")
    return db_analysis
