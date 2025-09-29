# services/bond_data_service/data_manager.py

import pandas as pd
import logging
from typing import Dict, Callable, Optional
import httpx
import json
import os

# 匯入我們新的資料庫工具和所有改造後的資料抓取器
from db_utils import load_series_from_db
from data_fetchers import (
    fred_sofr_fetcher,
    fred_dgs10_fetcher,
    fred_dgs2_fetcher,
    fred_rrp_fetcher,
    fred_vix_fetcher,
    fred_wresbal_fetcher,
    fred_hys_fetcher,
    nyfed_positions_fetcher
)

logger = logging.getLogger(__name__)

def _get_key_service_url() -> Optional[str]:
    """從服務註冊檔案中讀取 key_service 的 URL。"""
    try:
        with open("/tmp/service_registry.json", "r") as f:
            registry = json.load(f)
        key_service_info = registry.get("key_service")
        if key_service_info and "port" in key_service_info:
            return f"http://127.0.0.1:{key_service_info['port']}"
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass # 找不到或解析失敗時，靜默處理，返回 None
    return None

def _get_latest_fred_api_key() -> Optional[str]:
    """
    即時獲取 FRED API 金鑰，實現多源回退。
    優先順序: 1. key_service -> 2. 環境變數
    """
    key_service_url = _get_key_service_url()
    if key_service_url:
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{key_service_url}/api/keys/FRED_API_KEY/value")
                if response.status_code == 200:
                    api_key = response.json().get("key_value")
                    if api_key:
                        logger.info("即時從 key_service 獲取了 FRED API 金鑰。")
                        return api_key
        except httpx.RequestError:
            logger.warning("即時連接 key_service 失敗，將回退到環境變數。")

    # 如果 key_service 失敗或未設定，回退到環境變數
    api_key = os.getenv("FRED_API_KEY")
    if api_key:
        logger.info("從環境變數中獲取了 FRED API 金鑰。")
    return api_key


class DataManager:
    """
    負責管理所有金融數據的抓取與讀取，並實現了資料庫快取優先的邏輯。
    """
    def __init__(self):
        """
        初始化 DataManager。
        注意：API 金鑰現在是即時獲取的，不再於初始化時設定。
        """
        # 映射前端指標 ID 到後端抓取函式
        self._fetcher_map: Dict[str, Callable[..., pd.Series]] = {
            "sofr": fred_sofr_fetcher.fetch_sofr_data,
            "vix": fred_vix_fetcher.fetch_vix_data,
            "dgs10": fred_dgs10_fetcher.fetch_dgs10_data,
            "dgs2": fred_dgs2_fetcher.fetch_dgs2_data,
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
            "dgs10": "DGS10",
            "dgs2": "DGS2",
            "us_high_yield_spread": "HYG",
            "dealer_net_positions": "NYFED_TOTAL_POS",
            "dealer_long_term_positions": "NYFED_LONG_POS",
            "dealer_short_term_positions": "NYFED_SHORT_POS",
            "rrp": "RRPONTSYD",
            "wresbal": "WRESBAL",
        }

    def get_series(self, indicator_name: str, start_date: str, end_date: str, force_refresh: bool = False) -> Optional[pd.Series]:
        """
        獲取指定指標的時間序列數據，採用「快取優先」策略。

        1.  首先嘗試從本地 SQLite 資料庫讀取數據。
        2.  如果資料庫中沒有數據，或被要求強制刷新，則呼叫對應的網路抓取器。
        3.  抓取器會將從網路獲取的數據存入資料庫以供下次使用。

        Args:
            indicator_name (str): 內部使用的指標名稱 (例如 'sofr', 'vix')。
            start_date (str): 數據開始日期 (YYYY-MM-DD)。
            end_date (str): 數據結束日期 (YYYY-MM-DD)。
            force_refresh (bool): 如果為 True，則繞過快取，強制從網路抓取新數據。

        Returns:
            Optional[pd.Series]: 包含所請求數據的 pandas Series，如果無法獲取則返回 None。
        """
        db_ticker = self._ticker_map.get(indicator_name)
        if not db_ticker:
            logger.error(f"找不到指標 '{indicator_name}' 對應的資料庫 Ticker。")
            return None

        # 1. 檢查是否需要強制刷新，如果不需要，則嘗試從快取讀取
        if not force_refresh:
            cached_data = load_series_from_db(db_ticker, start_date, end_date)
            if cached_data is not None and not cached_data.empty:
                logger.info(f"指標 '{indicator_name}' 的數據從資料庫快取加載成功。")
                cached_data.name = indicator_name
                return cached_data

        # 2. 強制刷新或快取未命中，從網路抓取
        if force_refresh:
            logger.info(f"強制刷新指標 '{indicator_name}'，將從網路抓取。")
        else:
            logger.info(f"指標 '{indicator_name}' 在快取中未找到，將從網路抓取。")
        fetcher = self._fetcher_map.get(indicator_name)
        if not fetcher:
            logger.error(f"找不到指標 '{indicator_name}' 對應的資料抓取器。")
            return None

        try:
            # 準備傳遞給抓取器的參數
            fetcher_args = {"start_date": start_date, "end_date": end_date}

            # 判斷是否需要 API 金鑰
            # 修正：不再從 self.api_key 讀取，而是在需要時即時獲取
            if "fred_" in fetcher.__module__ or "nyfed_" in fetcher.__module__:
                latest_api_key = _get_latest_fred_api_key()
                if not latest_api_key:
                    logger.error(f"無法為指標 '{indicator_name}' 獲取有效的 API 金鑰，抓取中止。")
                    return None
                fetcher_args["api_key"] = latest_api_key

            # 呼叫抓取器
            fresh_data = fetcher(**fetcher_args)

            if fresh_data is None or fresh_data.empty:
                logger.warning(f"網路抓取器為指標 '{indicator_name}' 返回了空的 Series。")
                return None

            fresh_data.name = indicator_name
            return fresh_data

        except Exception as e:
            logger.error(f"為指標 '{indicator_name}' 執行資料抓取器時發生錯誤: {e}", exc_info=True)
            return None

    def check_api_key_status(self) -> bool:
        """
        公開方法，用於檢查 FRED API 金鑰是否有效且可獲取。

        Returns:
            bool: 如果金鑰成功獲取，則為 True，否則為 False。
        """
        logger.info("正在執行 API 金鑰狀態檢查...")
        key = _get_latest_fred_api_key()
        if key:
            logger.info("API 金鑰狀態檢查成功，金鑰已找到。")
            return True
        else:
            logger.warning("API 金鑰狀態檢查失敗，找不到金鑰。")
            return False