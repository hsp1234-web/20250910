# src/tools/data_fetchers/fred_cpi_fetcher.py

import pandas as pd
from fredapi import Fred

def fetch_cpi_data(api_key: str):
    """
    使用 FRED API 獲取美國 CPI (CPIAUCSL) 的時間序列資料。

    Args:
        api_key (str): FRED API 金鑰。

    Returns:
        pd.Series: 包含 CPI 資料的 pandas Series，索引為日期。
                   如果發生錯誤或找不到資料，則返回 None。
    """
    try:
        fred = Fred(api_key=api_key)
        cpi_series = fred.get_series('CPIAUCSL')

        if cpi_series.empty:
            print("警告：從 FRED API 未獲取到 CPI (CPIAUCSL) 數據。")
            return None

        cpi_series = cpi_series.dropna()
        cpi_series.name = 'cpi'

        print(f"成功從 FRED 獲取到 {len(cpi_series)} 筆 CPI (CPIAUCSL) 數據。")
        return cpi_series

    except Exception as e:
        print(f"錯誤：從 FRED API 獲取 CPI 數據時發生錯誤: {e}")
        return None
