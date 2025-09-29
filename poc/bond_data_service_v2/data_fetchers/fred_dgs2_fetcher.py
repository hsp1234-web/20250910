# services/bond_data_service/data_fetchers/fred_dgs2_fetcher.py
import pandas as pd
from fredapi import Fred
import logging
# 設置日誌
logger = logging.getLogger(__name__)

def fetch_dgs2_data(api_key: str, start_date: str, end_date: str) -> pd.Series:
    """
    使用 FRED API 獲取 2 年期美國公債固定期限利率 (DGS2) 在指定日期範圍內的資料。
    (注意：此函式現在只負責抓取，不再負責儲存。)
    Args:
        api_key (str): FRED API 金鑰。
        start_date (str): 開始日期 (YYYY-MM-DD)。
        end_date (str): 結束日期 (YYYY-MM-DD)。
    Returns:
        pd.Series: 包含 DGS2 資料的 pandas Series，索引為日期。
    """
    ticker = 'DGS2'
    series_name = 'dgs2'
    logger.info(f"抓取器：開始從 FRED 抓取 {ticker} ({start_date} to {end_date})...")

    try:
        fred = Fred(api_key=api_key)
        series = fred.get_series(ticker, observation_start=start_date, observation_end=end_date)

        if series.empty:
            logger.warning(f"抓取器：從 FRED API 未獲取到 {ticker} 數據。")
            return pd.Series(dtype='float64', name=series_name)

        series = series.dropna()
        series.index = pd.to_datetime(series.index).normalize()
        logger.info(f"抓取器：成功從 FRED 獲取到 {len(series)} 筆 {ticker} 數據。")

        series.name = series_name
        return series

    except Exception as e:
        logger.error(f"抓取器：從 FRED API 獲取 {ticker} 數據時發生錯誤: {e}", exc_info=True)
        return pd.Series(dtype='float64', name=series_name)