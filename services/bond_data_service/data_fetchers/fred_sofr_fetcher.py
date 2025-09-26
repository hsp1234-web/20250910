# services/bond_data_service/data_fetchers/fred_sofr_fetcher.py
import pandas as pd
from fredapi import Fred
import logging

# 設置日誌
logger = logging.getLogger(__name__)

def fetch_sofr_data(api_key: str):
    """
    使用 FRED API 獲取擔保隔夜融資利率 (SOFR) 的時間序列資料。

    Args:
        api_key (str): FRED API 金鑰。

    Returns:
        pd.Series: 包含 SOFR 資料的 pandas Series，索引為日期。
                   如果發生錯誤或找不到資料，則返回一個空的 Series。
    """
    try:
        fred = Fred(api_key=api_key)
        # 獲取 SOFR (代號: SOFR) 數據
        series = fred.get_series('SOFR')

        if series.empty:
            logger.warning("從 FRED API 未獲取到 SOFR 數據。")
            print("警告：從 FRED API 未獲取到 SOFR 數據。")
            return pd.Series(dtype='float64')

        # 數據清理
        series = series.dropna()
        series.name = 'sofr'

        # 標準化索引
        series.index = pd.to_datetime(series.index).normalize()

        logger.info(f"成功從 FRED 獲取到 {len(series)} 筆 SOFR 數據。")
        print(f"成功從 FRED 獲取到 {len(series)} 筆 SOFR 數據。")
        return series

    except Exception as e:
        logger.error(f"從 FRED API 獲取 SOFR 數據時發生錯誤: {e}", exc_info=True)
        print(f"錯誤：從 FRED API 獲取 SOFR 數據時發生錯誤: {e}")
        return pd.Series(dtype='float64')