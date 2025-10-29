# services/bond_fetcher_service/repository.py
import logging
import os
import sqlite3
import inspect
from pathlib import Path
from typing import Callable, Dict, Optional

import pandas as pd

# 匯入所有資料抓取器 (注意：現在的路徑是相對於此服務)
from .data_fetchers import (
    fred_sofr_fetcher,
    fred_dgs10_fetcher,
    fred_dgs2_fetcher,
    fred_rrp_fetcher,
    fred_vix_fetcher,
    fred_wresbal_fetcher,
    yahoo_hys_fetcher,
    nyfed_positions_fetcher,
)

logger = logging.getLogger(__name__)

# --- 資料庫設定 ---
# 為了職責分離，新服務將管理位於 bond_data_service 中的同一個資料庫檔案。
# 這確保了資料來源的統一性。
DB_FILE = Path(__file__).resolve().parent.parent / "bond_data_service" / "bond_data.sqlite3"

def initialize_database():
    """
    初始化資料庫。如果資料庫或資料表不存在，則建立它們。
    """
    logger.info(f"抓取器服務：正在確保資料庫存在於 {DB_FILE}...")
    try:
        # 確保目錄存在
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS time_series_data (
                date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                price REAL NOT NULL,
                PRIMARY KEY (date, ticker)
            )
            """)
            conn.commit()
        logger.info(f"✅ 抓取器服務：資料庫初始化完成。")
    except Exception as e:
        logger.error(f"❌ 抓取器服務：資料庫初始化失敗: {e}", exc_info=True)
        raise

def get_fred_api_key() -> Optional[str]:
    """
    從環境變數獲取 FRED API 金鑰。
    """
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        logger.warning("未找到環境變數 FRED_API_KEY。FRED 資料抓取將會失敗。")
    return api_key

class DataFetcherRepository:
    """
    專職的資料抓取與儲存倉儲。
    """
    def __init__(self):
        self._fetcher_map: Dict[str, Callable[..., pd.Series]] = {
            "sofr": fred_sofr_fetcher.fetch_sofr_data,
            "vix": fred_vix_fetcher.fetch_vix_data,
            "dgs10": fred_dgs10_fetcher.fetch_dgs10_data,
            "dgs2": fred_dgs2_fetcher.fetch_dgs2_data,
            "us_high_yield_spread": yahoo_hys_fetcher.fetch_hys_data,
            "dealer_net_positions": nyfed_positions_fetcher.fetch_nyfed_total_positions_data,
            "dealer_long_term_positions": nyfed_positions_fetcher.fetch_nyfed_long_term_positions_data,
            "dealer_short_term_positions": nyfed_positions_fetcher.fetch_nyfed_short_term_positions_data,
            "rrp": fred_rrp_fetcher.fetch_rrp_data,
            "wresbal": fred_wresbal_fetcher.fetch_wresbal_data,
        }
        self._ticker_map: Dict[str, str] = {
            "sofr": "SOFR", "vix": "VIXCLS", "dgs10": "DGS10", "dgs2": "DGS2",
            "us_high_yield_spread": "HYG", "dealer_net_positions": "NYFED_TOTAL_POS",
            "dealer_long_term_positions": "NYFED_LONG_POS", "dealer_short_term_positions": "NYFED_SHORT_POS",
            "rrp": "RRPONTSYD", "wresbal": "WRESBAL",
        }

    def _save_series_to_db(self, series: pd.Series, ticker: str):
        if not isinstance(series, pd.Series) or series.empty:
            return
        try:
            with sqlite3.connect(DB_FILE, timeout=10) as conn:
                data_to_insert = [
                    (idx.strftime('%Y-%m-%d'), ticker, val)
                    for idx, val in series.items() if pd.notna(val)
                ]
                if not data_to_insert: return
                sql = "INSERT OR REPLACE INTO time_series_data (date, ticker, price) VALUES (?, ?, ?)"
                conn.cursor().executemany(sql, data_to_insert)
                conn.commit()
                logger.info(f"成功將 {len(data_to_insert)} 筆 '{ticker}' 數據存入資料庫。")
        except sqlite3.Error as e:
            logger.error(f"儲存 '{ticker}' 數據時發生資料庫錯誤: {e}", exc_info=True)

    def fetch_and_store_series(self, indicator_name: str, start_date: str, end_date: str) -> bool:
        """
        核心方法：執行資料抓取並存入資料庫。
        返回 True 表示成功，False 表示失敗。
        """
        db_ticker = self._ticker_map.get(indicator_name)
        if not db_ticker:
            logger.error(f"找不到指標 '{indicator_name}' 對應的 Ticker。")
            return False

        fetcher = self._fetcher_map.get(indicator_name)
        if not fetcher:
            logger.error(f"找不到 '{indicator_name}' 的抓取器。")
            return False

        logger.info(f"開始從網路為 '{indicator_name}' 抓取資料...")
        try:
            fetcher_args = {"start_date": start_date, "end_date": end_date}
            sig = inspect.signature(fetcher)
            if 'api_key' in sig.parameters:
                api_key = get_fred_api_key()
                if not api_key:
                    logger.error(f"抓取 '{indicator_name}' 需要 FRED API 金鑰但未提供。")
                    return False
                fetcher_args["api_key"] = api_key

            fresh_data = fetcher(**fetcher_args)
            if fresh_data is not None and not fresh_data.empty:
                self._save_series_to_db(fresh_data, db_ticker)
                return True
            else:
                logger.warning(f"抓取 '{indicator_name}' 未返回任何數據。")
                return False
        except Exception as e:
            logger.error(f"抓取 '{indicator_name}' 時發生嚴重錯誤: {e}", exc_info=True)
            return False

    def get_all_indicator_names(self) -> list[str]:
        """提供所有可用的指標名稱列表。"""
        return list(self._ticker_map.keys())
