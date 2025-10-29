# src/tools/data_fetchers/fred_ism_fetcher.py

import pandas as pd
from fredapi import Fred

def fetch_ism_data(api_key: str):
    """
    使用 FRED API 獲取美國 ISM 製造業 PMI (NAPM) 的時間序列資料。

    Args:
        api_key (str): FRED API 金鑰。

    Returns:
        pd.Series: 包含 ISM PMI 資料的 pandas Series，索引為日期。
                   如果發生錯誤或找不到資料，則返回 None。
    """
    try:
        fred = Fred(api_key=api_key)
        ism_series = fred.get_series('NAPM')

        if ism_series.empty:
            print("警告：從 FRED API 未獲取到 ISM PMI (NAPM) 數據。")
            return None

        ism_series = ism_series.dropna()
        ism_series.name = 'ism'

        print(f"成功從 FRED 獲取到 {len(ism_series)} 筆 ISM PMI (NAPM) 數據。")
        print("最新 5 筆數據為:")
        print(ism_series.tail())
        return ism_series

    except Exception as e:
        print(f"錯誤：從 FRED API 獲取 ISM PMI 數據時發生錯誤: {e}")
        return None
