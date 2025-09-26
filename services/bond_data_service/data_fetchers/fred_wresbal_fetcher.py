# services/bond_data_service/data_fetchers/fred_wresbal_fetcher.py
import pandas as pd
from fredapi import Fred
import logging

# 設置日誌
logger = logging.getLogger(__name__)

def fetch_wresbal_data(api_key: str):
    """
    使用 FRED API 獲取聯邦儲備銀行準備金餘額 (WRESBAL) 的時間序列資料。
    注意：此為週頻數據。

    Args:
        api_key (str): FRED API 金鑰。

    Returns:
        pd.Series: 包含 WRESBAL 資料的 pandas Series，索引為日期。
                   如果發生錯誤或找不到資料，則返回一個空的 Series。
    """
    try:
        fred = Fred(api_key=api_key)
        # 獲取 WRESBAL (代號: WRESBAL) 數據
        series = fred.get_series('WRESBAL')

        if series.empty:
            logger.warning("從 FRED API 未獲取到 WRESBAL 數據。")
            print("警告：從 FRED API 未獲取到 WRESBAL 數據。")
            return pd.Series(dtype='float64')

        # 數據清理
        series = series.dropna()
        series.name = 'wresbal'

        # 標準化索引
        series.index = pd.to_datetime(series.index).normalize()

        logger.info(f"成功從 FRED 獲取到 {len(series)} 筆 WRESBAL 數據。")
        print(f"成功從 FRED 獲取到 {len(series)} 筆 WRESBAL 數據。")
        return series

    except Exception as e:
        logger.error(f"從 FRED API 獲取 WRESBAL 數據時發生錯誤: {e}", exc_info=True)
        print(f"錯誤：從 FRED API 獲取 WRESBAL 數據時發生錯誤: {e}")
        return pd.Series(dtype='float64')