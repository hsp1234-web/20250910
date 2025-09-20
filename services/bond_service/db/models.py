# -*- coding: utf-8 -*-
"""
資料庫模型 (SQLAlchemy ORM Models)

功能：
- 定義所有資料庫表格的結構。
"""
from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class AnalysisResult(Base):
    """
    分析結果資料表模型。
    用於儲存每一次非同步分析任務的狀態與結果。
    """
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 任務狀態: PENDING, SUCCESS, FAILURE
    status = Column(String, default="PENDING")

    # 輸入參數
    start_date = Column(String)
    end_date = Column(String)

    # 成功時的輸出
    stress_index_value = Column(Float, nullable=True)
    text_report = Column(Text, nullable=True)
    main_plot_base64 = Column(Text, nullable=True)

    # 失敗時的輸出
    error_message = Column(Text, nullable=True)

    def __repr__(self):
        return f"<AnalysisResult(id={self.id}, status='{self.status}')>"
