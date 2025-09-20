# services/bond_data_service/database.py

import sqlite3
from pathlib import Path

# 資料庫檔案路徑 (與 main.py 同級)
DATABASE_FILE = Path(__file__).resolve().parent / "bond_data.sqlite3"

def get_db_connection():
    """建立並返回一個資料庫連線。"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """
    初始化資料庫。如果資料表不存在，則建立它。
    """
    print("正在檢查並初始化資料庫...")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 建立宏觀經濟數據資料表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS macro_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            indicator TEXT NOT NULL,
            date TEXT NOT NULL,
            value REAL NOT NULL,
            UNIQUE(indicator, date)
        )
        """)

        conn.commit()
        conn.close()
        print("✅ 資料庫初始化完成。 `macro_data` 資料表已存在。")
    except Exception as e:
        print(f"❌ 資料庫初始化失敗: {e}")
        raise
