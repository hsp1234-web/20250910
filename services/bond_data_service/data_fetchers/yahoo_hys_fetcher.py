# services/bond_data_service/data_fetchers/fred_hys_fetcher.py

import pandas as pd
import yfinance as yf
import logging

# 確保日誌記錄器名稱與模組路徑一致
logger = logging.getLogger(__name__)

def fetch_hys_data(start_date: str, end_date: str) -> pd.Series:
    """
    (替代方案) 從 Yahoo Finance 抓取高收益債券 ETF (HYG) 在指定日期範圍內的歷史收盤價，
    作為高收益債市場情緒的替代指標，並將結果存入資料庫。

    Args:
        start_date (str): 開始日期 (YYYY-MM-DD).
        end_date (str): 結束日期 (YYYY-MM-DD).

    Returns:
        pd.Series: 包含 HYG 收盤價的時間序列，若抓取失敗則返回帶有正確名稱的空 Series。
                   Series 的名稱將被設為 'us_high_yield_spread' 以便與舊系統兼容。
    """
    ticker = "HYG"
    # 內部使用的系列名稱，以保持與系統其他部分的兼容性
    series_name = "us_high_yield_spread"
    logger.info(f"開始從 Yahoo Finance 抓取 {ticker} 數據 ({start_date} 至 {end_date})。")

    try:
        hyg_ticker = yf.Ticker(ticker)
        # 使用指定的日期範圍抓取數據
        hist = hyg_ticker.history(start=start_date, end=end_date)

        if hist.empty or 'Close' not in hist.columns:
            logger.warning(f"從 Yahoo Finance 抓取 '{ticker}' 數據時，返回的 DataFrame 為空或缺少 'Close' 欄。")
            return pd.Series(dtype='float64', name=series_name)

        hys_series = hist['Close']
        # 進行數據清理
        hys_series = hys_series.dropna()
        hys_series.index = pd.to_datetime(hys_series.index).tz_localize(None) # 確保移除時區

        logger.info(f"成功從 Yahoo Finance 抓取 {len(hys_series)} 筆 '{ticker}' 數據。")

        # 返回的 Series 應使用內部名稱 'us_high_yield_spread'
        hys_series.name = series_name
        return hys_series

    except Exception as e:
        logger.error(f"從 Yahoo Finance 抓取 '{ticker}' 數據時發生未預期的錯誤: {e}", exc_info=True)
        return pd.Series(dtype='float64', name=series_name)