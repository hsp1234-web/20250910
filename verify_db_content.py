import sqlite3
import logging
from pathlib import Path

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定義資料庫檔案的路徑
DB_FILE = Path(__file__).parent / 'financial_data.sqlite'

def verify_data():
    """
    連接到資料庫並驗證 'HYG' 數據是否已存入。
    """
    if not DB_FILE.exists():
        logging.error(f"驗證失敗：資料庫檔案不存在於 {DB_FILE}")
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # 查詢 'HYG' 數據的總筆數
        cursor.execute("SELECT COUNT(*) FROM time_series_data WHERE ticker = ?", ("HYG",))
        count = cursor.fetchone()[0]

        if count > 0:
            logging.info(f"驗證成功：在 'time_series_data' 表中找到 {count} 筆 'HYG' 的數據。")
        else:
            logging.error("驗證失敗：在資料庫中未找到 'HYG' 的數據。")

    except sqlite3.Error as e:
        logging.error(f"驗證數據時發生資料庫錯誤: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    verify_data()