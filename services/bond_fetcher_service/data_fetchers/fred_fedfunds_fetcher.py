# src/tools/data_fetchers/fred_fedfunds_fetcher.py

import pandas as pd
from fredapi import Fred

def fetch_fedfunds_data(api_key: str):
    """
    使用 FRED API 獲取聯準會基準利率 (FEDFUNDS) 的時間序列資料。

    Args:
        api_key (str): FRED API 金鑰。

    Returns:
        pd.Series: 包含聯準會基準利率資料的 pandas Series，索引為日期。
                   如果發生錯誤或找不到資料，則返回 None。
    """
    try:
        fred = Fred(api_key=api_key)
        fedfunds_series = fred.get_series('FEDFUNDS')

        if fedfunds_series.empty:
            print("警告：從 FRED API 未獲取到聯準會基準利率 (FEDFUNDS) 數據。")
            return None

        fedfunds_series = fedfunds_series.dropna()
        fedfunds_series.name = 'fedfunds'

        print(f"成功從 FRED 獲取到 {len(fedfunds_series)} 筆聯準會基準利率 (FEDFUNDS) 數據。")
        return fedfunds_series

    except Exception as e:
        print(f"錯誤：從 FRED API 獲取聯準會基準利率數據時發生錯誤: {e}")
        return None
