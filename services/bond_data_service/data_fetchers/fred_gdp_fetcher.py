# src/tools/data_fetchers/fred_gdp_fetcher.py

import pandas as pd
from fredapi import Fred

def fetch_gdp_data(api_key: str):
    """
    使用 FRED API 獲取美國實質 GDP (GDPC1) 的時間序列資料。

    Args:
        api_key (str): FRED API 金鑰。

    Returns:
        pd.Series: 包含 GDP 資料的 pandas Series，索引為日期。
                   如果發生錯誤或找不到資料，則返回 None。
    """
    try:
        # 初始化 FRED API
        fred = Fred(api_key=api_key)

        # 獲取 GDP (代號: GDPC1) 數據
        # GDPC1 是季度數據，FRED 會返回每個季度的第一天作為日期
        gdp_series = fred.get_series('GDPC1')

        if gdp_series.empty:
            print("警告：從 FRED API 未獲取到 GDP (GDPC1) 數據。")
            return None

        # 數據清理
        gdp_series = gdp_series.dropna()
        gdp_series.name = 'gdp'

        print(f"成功從 FRED 獲取到 {len(gdp_series)} 筆 GDP (GDPC1) 數據。")
        return gdp_series

    except Exception as e:
        print(f"錯誤：從 FRED API 獲取 GDP 數據時發生錯誤: {e}")
        return None
