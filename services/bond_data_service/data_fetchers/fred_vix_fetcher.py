# services/bond_data_service/data_fetchers/fred_vix_fetcher.py
import pandas as pd
from fredapi import Fred
import logging
from ..db_utils import save_series_to_db

# 設置日誌
logger = logging.getLogger(__name__)

def fetch_vix_data(api_key: str, start_date: str, end_date: str) -> pd.Series:
    """
    使用 FRED API 獲取 CBOE 波動率指數 (VIXCLS) 在指定日期範圍內的資料，並存入資料庫。

    Args:
        api_key (str): FRED API 金鑰。
        start_date (str): 開始日期 (YYYY-MM-DD)。
        end_date (str): 結束日期 (YYYY-MM-DD)。

    Returns:
        pd.Series: 包含 VIX 資料的 pandas Series，索引為日期。
                   如果發生錯誤或找不到資料，則返回一個空的 Series。
    """
    ticker = 'VIXCLS'
    series_name = 'vix'
    logger.info(f"開始從 FRED 抓取 {ticker} 數據 ({start_date} 至 {end_date})。")

    try:
        fred = Fred(api_key=api_key)
        series = fred.get_series(ticker, observation_start=start_date, observation_end=end_date)

        if series.empty:
            logger.warning(f"從 FRED API 未獲取到 {ticker} 數據。")
            return pd.Series(dtype='float64', name=series_name)

        series = series.dropna()
        series.index = pd.to_datetime(series.index).normalize()

        logger.info(f"成功從 FRED 獲取到 {len(series)} 筆 {ticker} 數據。")

        save_series_to_db(series, ticker)

        series.name = series_name
        return series

    except Exception as e:
        logger.error(f"從 FRED API 獲取 {ticker} 數據時發生錯誤: {e}", exc_info=True)
        return pd.Series(dtype='float64', name=series_name)