# services/bond_data_service/data_fetchers/fred_hys_fetcher.py

import pandas as pd
import yfinance as yf
import logging
# 確保日誌記錄器名稱與模組路徑一致
logger = logging.getLogger(__name__)

def fetch_hys_data(start_date: str, end_date: str) -> pd.Series:
    """
    (替代方案) 從 Yahoo Finance 抓取高收益債券 ETF (HYG) 的歷史收盤價。
    (注意：此函式現在只負責抓取，不再負責儲存。)
    Args:
        start_date (str): 開始日期 (YYYY-MM-DD).
        end_date (str): 結束日期 (YYYY-MM-DD).
    Returns:
        pd.Series: 包含 HYG 收盤價的時間序列。
    """
    ticker = "HYG"
    series_name = "us_high_yield_spread"
    logger.info(f"抓取器：開始從 Yahoo Finance 抓取 {ticker} ({start_date} to {end_date})...")

    try:
        hyg_ticker = yf.Ticker(ticker)
        hist = hyg_ticker.history(start=start_date, end=end_date)

        if hist.empty or 'Close' not in hist.columns:
            logger.warning(f"抓取器：從 Yahoo Finance 抓取 '{ticker}' 時返回空資料。")
            return pd.Series(dtype='float64', name=series_name)

        hys_series = hist['Close'].dropna()
        hys_series.index = pd.to_datetime(hys_series.index).tz_localize(None)
        logger.info(f"抓取器：成功從 Yahoo Finance 抓取 {len(hys_series)} 筆 '{ticker}' 數據。")

        hys_series.name = series_name
        return hys_series

    except Exception as e:
        logger.error(f"抓取器：從 Yahoo Finance 抓取 '{ticker}' 數據時發生錯誤: {e}", exc_info=True)
        return pd.Series(dtype='float64', name=series_name)