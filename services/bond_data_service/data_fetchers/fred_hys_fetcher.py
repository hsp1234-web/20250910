# services/bond_data_service/data_fetchers/fred_hys_fetcher.py

import pandas as pd
from fredapi import Fred
import logging

# 確保日誌記錄器名稱與模組路徑一致
logger = logging.getLogger(__name__)

def fetch_hys_data(api_key: str) -> pd.Series:
    """
    從 FRED 抓取美國高收益債利差 (BofA US High Yield Index Option-Adjusted Spread)。
    序列 ID: BAMLH0A0HYM2

    Args:
        api_key (str): 用於 FRED API 驗證的金鑰。

    Returns:
        pd.Series: 包含高收益債利差數據的時間序列，若抓取失敗則返回帶有正確名稱的空 Series。
    """
    # 檢查 API 金鑰是否為預設的無效金鑰或空值
    if not api_key or "YOUR_DEFAULT_API_KEY" in api_key:
        logger.warning("未提供有效的 FRED API 金鑰，將跳過高收益債利差數據的抓取。")
        return pd.Series(dtype='float64', name='us_high_yield_spread')

    try:
        fred = Fred(api_key=api_key)
        hys_series = fred.get_series('BAMLH0A0HYM2')
        hys_series.name = 'us_high_yield_spread'

        # 進行數據清理
        hys_series = hys_series.dropna()
        hys_series.index = pd.to_datetime(hys_series.index)

        logger.info(f"成功從 FRED 抓取 {len(hys_series)} 筆高收益債利差數據。")
        return hys_series
    except ValueError as e:
        # fredapi 在金鑰無效時會引發 ValueError，我們在這裡特別捕捉它
        logger.warning(f"從 FRED 抓取高收益債利差數據時發生錯誤，很可能是 API 金鑰無效或已過期: {e}")
        return pd.Series(dtype='float64', name='us_high_yield_spread')
    except Exception as e:
        # 處理其他可能的網路或 API 錯誤
        logger.error(f"從 FRED 抓取高收益債利差數據時發生未預期的錯誤: {e}", exc_info=True)
        return pd.Series(dtype='float64', name='us_high_yield_spread')