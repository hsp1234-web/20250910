# src/api/dependencies.py
import sqlite3
import sys
from pathlib import Path

# 修正路徑以導入專案模組
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from db import database

# V7.0 重構: 移除 DBClient，改為直接資料庫連線
# from db.client import DBClient
# db_client = DBClient()

def get_db():
    """
    FastAPI 依賴項，為每個請求提供一個獨立的資料庫連線。
    使用 'yield' 來確保連線在請求結束後能被妥善關閉。
    """
    conn = None
    try:
        conn = database.get_db_connection()
        yield conn
    finally:
        if conn:
            conn.close()
