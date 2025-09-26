# services/bond_data_service/data_fetchers/fred_dgs2_fetcher.py
import pandas as pd
from fredapi import Fred
import logging

# 設置日誌
logger = logging.getLogger(__name__)

def fetch_dgs2_data(api_key: str):
    """
    使用 FRED API 獲取 2 年期美國公債固定期限利率 (DGS2) 的時間序列資料。

    Args:
        api_key (str): FRED API 金鑰。

    Returns:
        pd.Series: 包含 DGS2 資料的 pandas Series，索引為日期。
                   如果發生錯誤或找不到資料，則返回一個空的 Series。
    """
    try:
        fred = Fred(api_key=api_key)
        # 獲取 DGS2 (代號: DGS2) 數據
        series = fred.get_series('DGS2')

        if series.empty:
            logger.warning("從 FRED API 未獲取到 DGS2 數據。")
            print("警告：從 FRED API 未獲取到 DGS2 數據。")
            return pd.Series(dtype='float64')

        # 數據清理
        series = series.dropna()
        series.name = 'dgs2'

        # 標準化索引
        series.index = pd.to_datetime(series.index).normalize()

        logger.info(f"成功從 FRED 獲取到 {len(series)} 筆 DGS2 數據。")
        print(f"成功從 FRED 獲取到 {len(series)} 筆 DGS2 數據。")
        return series

    except Exception as e:
        logger.error(f"從 FRED API 獲取 DGS2 數據時發生錯誤: {e}", exc_info=True)
        print(f"錯誤：從 FRED API 獲取 DGS2 數據時發生錯誤: {e}")
        return pd.Series(dtype='float64')