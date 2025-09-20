# -*- coding: utf-8 -*-
"""
資料庫 CRUD (Create, Read, Update, Delete) 操作

功能：
- 提供與資料庫互動的函式，將資料庫操作與 API 路由邏輯分離。
"""
from sqlalchemy.orm import Session
from . import models

def get_analysis(db: Session, analysis_id: int):
    """
    根據 ID 讀取一筆分析結果。
    """
    return db.query(models.AnalysisResult).filter(models.AnalysisResult.id == analysis_id).first()

def create_analysis(db: Session, start_date: str, end_date: str) -> models.AnalysisResult:
    """
    建立一筆新的分析任務紀錄，初始狀態為 PENDING。
    """
    db_analysis = models.AnalysisResult(
        start_date=start_date,
        end_date=end_date,
        status="PENDING"
    )
    db.add(db_analysis)
    db.commit()
    db.refresh(db_analysis)
    return db_analysis

def update_analysis_success(db: Session, analysis_id: int, results: dict):
    """
    使用成功的分析結果更新紀錄。
    """
    db_analysis = get_analysis(db, analysis_id)
    if db_analysis:
        db_analysis.status = "SUCCESS"
        db_analysis.stress_index_value = results.get("stress_index_value")
        db_analysis.text_report = results.get("text_report")
        db_analysis.main_plot_base64 = results.get("main_plot_base64")
        db.commit()
        db.refresh(db_analysis)
    return db_analysis

def update_analysis_failure(db: Session, analysis_id: int, error_message: str):
    """
    使用失敗的錯誤訊息更新紀錄。
    """
    db_analysis = get_analysis(db, analysis_id)
    if db_analysis:
        db_analysis.status = "FAILURE"
        db_analysis.error_message = error_message
        db.commit()
        db.refresh(db_analysis)
    return db_analysis
