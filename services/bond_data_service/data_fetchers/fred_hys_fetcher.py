# services/bond_data_service/data_fetchers/fred_hys_fetcher.py

import pandas as pd
import yfinance as yf
import logging
import sqlite3
from pathlib import Path

# 確保日誌記錄器名稱與模組路徑一致
logger = logging.getLogger(__name__)

# 定義資料庫檔案的路徑 (相對於此檔案的位置)
# __file__ -> .../services/bond_data_service/data_fetchers/fred_hys_fetcher.py
# .parent -> .../data_fetchers
# .parent.parent -> .../bond_data_service
# .parent.parent.parent -> .../services
# .parent.parent.parent.parent -> /app (專案根目錄)
DB_FILE = Path(__file__).resolve().parent.parent.parent.parent / 'financial_data.sqlite'

def save_series_to_db(series: pd.Series, ticker: str):
    """
    將時間序列數據儲存到 SQLite 資料庫。

    使用 'INSERT OR REPLACE' 語句，如果數據已存在 (基於日期和 ticker)，則會更新它。

    Args:
        series (pd.Series): 要儲存的時間序列數據 (索引應為 DatetimeIndex)。
        ticker (str): 該數據的標的代碼。
    """
    if series.empty:
        logger.info(f"標的 '{ticker}' 的數據序列為空，跳過資料庫儲存。")
        return

    if not DB_FILE.exists():
        logger.error(f"資料庫檔案不存在於: {DB_FILE}。請先執行 create_database.py。")
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # 準備要插入的數據，格式為 (日期字串, 標的代碼, 價格)
        data_to_insert = [
            (idx.strftime('%Y-%m-%d'), ticker, val)
            for idx, val in series.items()
        ]

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

def fetch_hys_data() -> pd.Series:
    """
    (POC 替代方案) 從 Yahoo Finance 抓取高收益債券 ETF (HYG) 的歷史收盤價，
    作為高收益債市場情緒的替代指標，並將結果存入資料庫。

    Returns:
        pd.Series: 包含 HYG 收盤價的時間序列，若抓取失敗則返回帶有正確名稱的空 Series。
                   Series 的名稱將被設為 'us_high_yield_spread' 以便與舊系統兼容。
    """
    ticker = "HYG"
    series_name = "us_high_yield_spread"
    logger.info(f"開始從 Yahoo Finance 抓取 {ticker} 數據作為 '{series_name}' 的替代。")

    try:
        hyg_ticker = yf.Ticker(ticker)
        hist = hyg_ticker.history(period="max")

        if hist.empty or 'Close' not in hist.columns:
            logger.warning(f"從 Yahoo Finance 抓取 '{ticker}' 數據時，返回的 DataFrame 為空或缺少 'Close' 欄。")
            return pd.Series(dtype='float64', name=series_name)

        hys_series = hist['Close']
        hys_series.name = series_name
        hys_series = hys_series.dropna()
        hys_series.index = pd.to_datetime(hys_series.index).tz_localize(None) # 確保移除時區

        logger.info(f"成功從 Yahoo Finance 抓取 {len(hys_series)} 筆 '{ticker}' 數據。")

        # 抓取成功後，將數據儲存到資料庫
        save_series_to_db(hys_series, ticker)

        return hys_series

    except Exception as e:
        logger.error(f"從 Yahoo Finance 抓取 '{ticker}' 數據時發生未預期的錯誤: {e}", exc_info=True)
        return pd.Series(dtype='float64', name=series_name)