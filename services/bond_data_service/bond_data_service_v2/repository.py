# services/bond_data_service/bond_data_service_v2/repository.py

import logging
import os
import sqlite3
import inspect
from pathlib import Path
from typing import Callable, Dict, Optional
import sys # JULES: 新增

import pandas as pd

# JULES: 新增路徑修正，以便能從主應用程式匯入 key_manager
# 這個路徑向上跳了五層，到達專案根目錄，然後再進入 src
# services/bond_data_service/bond_data_service_v2/repository.py -> ... -> services/ -> root
SRC_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from core import key_manager # JULES: 匯入中央金鑰管理器

# 匯入所有資料抓取器
from .data_fetchers import (
    fred_sofr_fetcher,
    fred_dgs10_fetcher,
    fred_dgs2_fetcher,
    fred_rrp_fetcher,
    fred_vix_fetcher,
    fred_wresbal_fetcher,
    fred_hys_fetcher,
    nyfed_positions_fetcher,
)

logger = logging.getLogger(__name__)

# --- 資料庫設定與初始化 ---

DB_FILE = Path(__file__).resolve().parent / "bond_data.sqlite3"

def initialize_database():
    """
    初始化資料庫。如果資料庫或資料表不存在，則建立它們。
    """
    logger.info("正在檢查並初始化 bond_data_service 的資料庫...")
    try:
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
        logger.info(f"✅ bond_data_service 資料庫初始化完成，檔案位於: {DB_FILE}")
    except Exception as e:
        logger.error(f"❌ bond_data_service 資料庫初始化失敗: {e}", exc_info=True)
        raise

# JULES (2025-09-29): 移除 get_fred_api_key 函式。
# 金鑰現在將由中央 key_manager 提供。

# --- 倉儲層核心類 ---

class FinancialDataRepository:
    """
    資料的唯一守門員，負責所有資料的持久化和存取。
    """

    def __init__(self):
        """
        初始化倉儲。
        """
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
        self._ticker_map: Dict[str, str] = {
            "sofr": "SOFR",
            "vix": "VIXCLS",
            "dgs10": "DGS10",
            "dgs2": "DGS2",
            "us_high_yield_spread": "BAMLH0A0HYM2",
            "dealer_net_positions": "NYFED_TOTAL_POS",
            "dealer_long_term_positions": "NYFED_LONG_POS",
            "dealer_short_term_positions": "NYFED_SHORT_POS",
            "rrp": "RRPONTSYD",
            "wresbal": "WRESBAL",
        }

    def _save_series_to_db(self, series: pd.Series, ticker: str):
        """
        將時間序列數據儲存到 SQLite 資料庫。
        """
        if not isinstance(series, pd.Series) or series.empty:
            return
        try:
            with sqlite3.connect(DB_FILE, timeout=10) as conn:
                data_to_insert = [
                    (idx.strftime('%Y-%m-%d'), ticker, val)
                    for idx, val in series.items() if pd.notna(val)
                ]
                if not data_to_insert:
                    return
                sql = "INSERT OR REPLACE INTO time_series_data (date, ticker, price) VALUES (?, ?, ?)"
                conn.cursor().executemany(sql, data_to_insert)
                conn.commit()
                logger.info(f"成功將 {len(data_to_insert)} 筆 '{ticker}' 數據存入資料庫。")
        except sqlite3.Error as e:
            logger.error(f"儲存 '{ticker}' 數據時發生資料庫錯誤: {e}", exc_info=True)

    def _load_series_from_db(self, ticker: str, start_date: str, end_date: str) -> Optional[pd.Series]:
        """
        從 SQLite 資料庫讀取時間序列數據。
        """
        if not DB_FILE.exists():
            return None
        try:
            with sqlite3.connect(DB_FILE) as conn:
                query = "SELECT date, price FROM time_series_data WHERE ticker = ? AND date BETWEEN ? AND ? ORDER BY date ASC"
                df = pd.read_sql_query(query, conn, params=(ticker, start_date, end_date), index_col='date', parse_dates=['date'])
                if df.empty:
                    return None
                series = df['price']
                series.name = ticker
                logger.info(f"成功從資料庫快取讀取 {len(series)} 筆 '{ticker}' 的數據。")
                return series
        except (sqlite3.Error, pd.errors.DatabaseError) as e:
            logger.error(f"讀取 '{ticker}' 數據時發生資料庫錯誤: {e}", exc_info=True)
            return None

    def get_series(self, indicator_name: str, start_date: str, end_date: str, force_refresh: bool = False) -> Optional[pd.Series]:
        """
        獲取指定指標的時間序列數據，採用「快取優先」策略。
        """
        db_ticker = self._ticker_map.get(indicator_name)
        if not db_ticker:
            logger.error(f"找不到指標 '{indicator_name}' 對應的資料庫 Ticker。")
            return None

        if not force_refresh:
            cached_data = self._load_series_from_db(db_ticker, start_date, end_date)
            if cached_data is not None:
                cached_data.name = indicator_name
                return cached_data

        logger.info(f"快取未命中或強制刷新，從網路抓取 '{indicator_name}'。")
        fetcher = self._fetcher_map.get(indicator_name)
        if not fetcher:
            logger.error(f"找不到 '{indicator_name}' 的抓取器。")
            return None

        try:
            fetcher_args = {"start_date": start_date, "end_date": end_date}

            sig = inspect.signature(fetcher)
            if 'api_key' in sig.parameters:
                # JULES: 從中央管理器獲取 FRED 金鑰
                api_key = key_manager.get_valid_key_by_type('fred')
                if not api_key:
                    logger.error(f"抓取 '{indicator_name}' 需要 FRED API 金鑰，但中央管理器中沒有可用的有效金鑰。操作中止。")
                    return None
                fetcher_args["api_key"] = api_key

            fresh_data = fetcher(**fetcher_args)
            if fresh_data is not None and not fresh_data.empty:
                self._save_series_to_db(fresh_data, db_ticker)
                fresh_data.name = indicator_name
                return fresh_data
            return None
        except Exception as e:
            logger.error(f"抓取 '{indicator_name}' 時發生錯誤: {e}", exc_info=True)
            return None

    def check_api_key_status(self) -> bool:
        """
        檢查中央管理器中是否有可用的 FRED API 金鑰。
        """
        # JULES: 使用中央管理器檢查金鑰狀態
        return key_manager.get_valid_key_by_type('fred') is not None