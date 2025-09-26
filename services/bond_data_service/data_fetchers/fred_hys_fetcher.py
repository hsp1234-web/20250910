# services/bond_data_service/data_fetchers/fred_hys_fetcher.py

import pandas as pd
from fredapi import Fred
import logging

logger = logging.getLogger(__name__)

def fetch_hys_data(api_key: str) -> pd.Series:
    """
    從 FRED 抓取美國高收益債利差 (BofA US High Yield Index Option-Adjusted Spread)。
    序列 ID: BAMLH0A0HYM2
    """
    try:
        fred = Fred(api_key=api_key)
        hys_series = fred.get_series('BAMLH0A0HYM2')
        hys_series.name = 'us_high_yield_spread'

        # 進行數據清理
        hys_series = hys_series.dropna()
        hys_series.index = pd.to_datetime(hys_series.index)

        logger.info(f"成功從 FRED 抓取 {len(hys_series)} 筆高收益債利差數據。")
        print(f"成功抓取 {len(hys_series)} 筆高收益債利差數據。")
        return hys_series
    except Exception as e:
        logger.error(f"從 FRED 抓取高收益債利差數據時發生錯誤: {e}", exc_info=True)
        return pd.Series(dtype='float64')