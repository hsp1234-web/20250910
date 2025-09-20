# -*- coding: utf-8 -*-
"""
資料庫連線與 Session 管理

功能：
- 設定資料庫 URL (使用 SQLite)。
- 建立 SQLAlchemy 引擎 (engine)。
- 建立 SessionLocal 工廠以生成資料庫 session。
- 提供 Declarative Base 以供模型繼承。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

# --- 資料庫設定 ---
# 使用位於服務目錄下的 SQLite 資料庫檔案
DATABASE_URL = "sqlite:///./services/bond_service/bond_data.sqlite3"

# 建立 SQLAlchemy 引擎
# connect_args 是 SQLite 特有的設定，用於允許多執行緒操作
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

# 建立 SessionLocal 工廠
# autocommit=False 和 autoflush=False 是標準的 API 使用模式
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """
    初始化資料庫，建立所有表格。
    """
    # 根據模型定義，在資料庫中建立所有表格
    Base.metadata.create_all(bind=engine)
