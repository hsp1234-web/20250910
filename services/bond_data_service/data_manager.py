# services/bond_data_service/data_manager.py

import pandas as pd
import logging
from typing import Dict, Callable, Optional

# 匯入我們新的資料庫工具和所有改造後的資料抓取器
from .db_utils import load_series_from_db
from .data_fetchers import (
    fred_sofr_fetcher,
    fred_dgs10_fetcher,
    fred_dgs2_fetcher,
    fred_dgs5_fetcher,
    fred_dgs30_fetcher,
    fred_dgs3mo_fetcher,
    fred_rrp_fetcher,
    fred_vix_fetcher,
    fred_wresbal_fetcher,
    fred_hys_fetcher,
    nyfed_positions_fetcher
)

logger = logging.getLogger(__name__)

class DataManager:
    """
    負責管理所有金融數據的抓取與讀取，並實現了資料庫快取優先的邏輯。
    """
    def __init__(self, api_key: str):
        """
        初始化 DataManager。

        Args:
            api_key (str): FRED API 金鑰，用於需要它的資料抓取器。
        """
        self.api_key = api_key

        # 映射前端指標 ID 到後端抓取函式
        self._fetcher_map: Dict[str, Callable[..., pd.Series]] = {
            "sofr": fred_sofr_fetcher.fetch_sofr_data,
            "vix": fred_vix_fetcher.fetch_vix_data,
            "dgs30": fred_dgs30_fetcher.fetch_dgs30_data,
            "dgs10": fred_dgs10_fetcher.fetch_dgs10_data,
            "dgs5": fred_dgs5_fetcher.fetch_dgs5_data,
            "dgs2": fred_dgs2_fetcher.fetch_dgs2_data,
            "dgs3mo": fred_dgs3mo_fetcher.fetch_dgs3mo_data,
            "us_high_yield_spread": fred_hys_fetcher.fetch_hys_data,
            "dealer_net_positions": nyfed_positions_fetcher.fetch_nyfed_total_positions_data,
            "dealer_long_term_positions": nyfed_positions_fetcher.fetch_nyfed_long_term_positions_data,
            "dealer_short_term_positions": nyfed_positions_fetcher.fetch_nyfed_short_term_positions_data,
            "rrp": fred_rrp_fetcher.fetch_rrp_data,
            "wresbal": fred_wresbal_fetcher.fetch_wresbal_data,
        }

        # 映射前端指標 ID 到資料庫中儲存的 Ticker 名稱
        self._ticker_map: Dict[str, str] = {
            "sofr": "SOFR",
            "vix": "VIXCLS",
            "dgs30": "DGS30",
            "dgs10": "DGS10",
            "dgs5": "DGS5",
            "dgs2": "DGS2",
            "dgs3mo": "DGS3MO",
            "us_high_yield_spread": "HYG",
            "dealer_net_positions": "NYFED_TOTAL_POS",
            "dealer_long_term_positions": "NYFED_LONG_POS",
            "dealer_short_term_positions": "NYFED_SHORT_POS",
            "rrp": "RRPONTSYD",
            "wresbal": "WRESBAL",
        }

    def get_series(self, indicator_name: str, start_date: str, end_date: str) -> Optional[pd.Series]:
        """
        獲取指定指標的時間序列數據，採用「快取優先」策略。
        """
        db_ticker = self._ticker_map.get(indicator_name)
        if not db_ticker:
            logger.error(f"找不到指標 '{indicator_name}' 對應的資料庫 Ticker。")
            return None

        # 1. 嘗試從資料庫快取讀取
        cached_data = load_series_from_db(db_ticker, start_date, end_date)
        if cached_data is not None and not cached_data.empty:
            logger.info(f"指標 '{indicator_name}' 的數據從資料庫快取加載成功。")
            cached_data.name = indicator_name
            return cached_data

        # 2. 快取未命中，從網路抓取
        logger.info(f"指標 '{indicator_name}' 在快取中未找到，將從網路抓取。")
        fetcher = self._fetcher_map.get(indicator_name)
        if not fetcher:
            logger.error(f"找不到指標 '{indicator_name}' 對應的資料抓取器。")
            return None

        try:
            fetcher_args = {"start_date": start_date, "end_date": end_date}

            if "fred" in fetcher.__module__:
                fetcher_args["api_key"] = self.api_key

            fresh_data = fetcher(**fetcher_args)

            if fresh_data is None or fresh_data.empty:
                logger.warning(f"網路抓取器為指標 '{indicator_name}' 返回了空的 Series。")
                return None

            fresh_data.name = indicator_name
            return fresh_data

        except Exception as e:
            logger.error(f"為指標 '{indicator_name}' 執行資料抓取器時發生錯誤: {e}", exc_info=True)
            return None