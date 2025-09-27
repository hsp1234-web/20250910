# services/bond_data_service/db_utils.py

import sqlite3
import logging
from pathlib import Path
import pandas as pd
from typing import Optional

# 設定日誌
logger = logging.getLogger(__name__)

# 定義資料庫檔案的絕對路徑
# __file__ -> .../services/bond_data_service/db_utils.py
# .parent.parent.parent -> /app (專案根目錄)
DB_FILE = Path(__file__).resolve().parent.parent.parent / 'financial_data.sqlite'

def save_series_to_db(series: pd.Series, ticker: str):
    """
    將時間序列數據儲存到 SQLite 資料庫。

    使用 'INSERT OR REPLACE' 語句，如果數據已存在 (基於日期和 ticker)，則會更新它。

    Args:
        series (pd.Series): 要儲存的時間序列數據 (索引應為 DatetimeIndex)。
        ticker (str): 該數據的標的代碼。
    """
    if series.empty:
        logger.debug(f"標的 '{ticker}' 的數據序列為空，跳過資料庫儲存。")
        return

    if not DB_FILE.exists():
        logger.error(f"資料庫檔案不存在於: {DB_FILE}。請先執行 create_database.py。")
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10) # 增加超時
        cursor = conn.cursor()

        # 準備要插入的數據，格式為 (日期字串, 標的代碼, 價格)
        data_to_insert = [
            (idx.strftime('%Y-%m-%d'), ticker, val)
            for idx, val in series.items() if pd.notna(val) # 確保不插入 NaN
        ]

        if not data_to_insert:
            logger.debug(f"標的 '{ticker}' 的數據序列在移除 NaN 後為空，跳過儲存。")
            return

        # 使用 INSERT OR REPLACE 處理已存在的數據，避免重複插入錯誤
        sql = "INSERT OR REPLACE INTO time_series_data (date, ticker, price) VALUES (?, ?, ?)"
        cursor.executemany(sql, data_to_insert)
        conn.commit()
        logger.info(f"成功將 {len(data_to_insert)} 筆 '{ticker}' 的數據儲存/更新至資料庫。")

    except sqlite3.Error as e:
        logger.error(f"儲存 '{ticker}' 數據時發生資料庫錯誤: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

def load_series_from_db(ticker: str, start_date: str, end_date: str) -> Optional[pd.Series]:
    """
    從 SQLite 資料庫讀取指定日期範圍內的時間序列數據。

    Args:
        ticker (str): 要讀取的標的代碼。
        start_date (str): 開始日期 (YYYY-MM-DD)。
        end_date (str): 結束日期 (YYYY-MM-DD)。

    Returns:
        Optional[pd.Series]: 包含數據的時間序列，如果找不到數據或發生錯誤則返回 None。
    """
    if not DB_FILE.exists():
        logger.warning(f"資料庫檔案不存在於: {DB_FILE}，無法讀取快取。")
        return None

    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        # 使用 read_sql_query 可以方便地將查詢結果直接轉為 DataFrame
        query = """
            SELECT date, price FROM time_series_data
            WHERE ticker = ? AND date BETWEEN ? AND ?
            ORDER BY date ASC
        """
        params = (ticker, start_date, end_date)
        df = pd.read_sql_query(query, conn, params=params, index_col='date', parse_dates=['date'])

        if df.empty:
            logger.info(f"在資料庫快取中未找到標的 '{ticker}' 在 {start_date} 至 {end_date} 的數據。")
            return None

        series = df['price']
        series.name = ticker
        logger.info(f"成功從資料庫快取中讀取 {len(series)} 筆 '{ticker}' 的數據。")
        return series

    except (sqlite3.Error, pd.errors.DatabaseError) as e:
        logger.error(f"讀取 '{ticker}' 數據時發生資料庫錯誤: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()