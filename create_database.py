# create_database.py

import sqlite3
import logging
from pathlib import Path

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定義資料庫檔案的路徑
DB_FILE = Path(__file__).parent / 'financial_data.sqlite'

def initialize_database():
    """
    初始化 SQLite 資料庫。

    如果資料庫檔案不存在，則會建立它。
    如果 'time_series_data' 資料表不存在，則會建立它。
    """
    logging.info(f"正在檢查並初始化資料庫: {DB_FILE}")

    try:
        # 建立與資料庫的連接 (如果檔案不存在，會自動建立)
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # 檢查 'time_series_data' 資料表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master WHERE type='table' AND name='time_series_data'
        """)
        if cursor.fetchone() is None:
            logging.info("資料表 'time_series_data' 不存在，正在建立...")
            # 建立資料表
            # - date: ISO 8601 格式的日期 (TEXT)，作為主鍵的一部分
            # - ticker: 標的代碼 (TEXT)，作為主鍵的一部分
            # - price: 收盤價 (REAL)
            # - created_at: 記錄建立時間 (TIMESTAMP)
            cursor.execute("""
                CREATE TABLE time_series_data (
                    date TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    price REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (date, ticker)
                )
            """)
            logging.info("資料表 'time_series_data' 建立成功。")
        else:
            logging.info("資料表 'time_series_data' 已存在，無需建立。")

        # 提交變更並關閉連接
        conn.commit()
        conn.close()
        logging.info("資料庫初始化完成。")

    except sqlite3.Error as e:
        logging.error(f"資料庫操作時發生錯誤: {e}", exc_info=True)
    except Exception as e:
        logging.error(f"初始化資料庫時發生未預期的錯誤: {e}", exc_info=True)

if __name__ == '__main__':
    # 當直接執行此腳本時，調用初始化函式
    initialize_database()