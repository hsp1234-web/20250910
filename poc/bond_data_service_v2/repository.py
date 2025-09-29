# poc/bond_data_service_v2/repository.py
# 繁體中文註解：資料倉儲層

import logging
import sqlite3
from pathlib import Path
from typing import Callable, Dict, Optional

import httpx
import json
import os
import pandas as pd

# 導入所有資料抓取器
from .data_fetchers import (
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

# --- 常數定義 ---

# 資料庫檔案路徑
DB_FILE = Path(__file__).resolve().parent / 'bond_data.sqlite3'

# 映射內部指標名稱到資料庫中的 Ticker 名稱
TICKER_MAP: Dict[str, str] = {
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

# 映射內部指標名稱到後端抓取函式
FETCHER_MAP: Dict[str, Callable[..., pd.Series]] = {
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

# --- 私有輔助函式 ---

def _get_key_service_url() -> Optional[str]:
    """從服務註冊檔案中讀取 key_service 的 URL。"""
    try:
        with open("/tmp/service_registry.json", "r") as f:
            registry = json.load(f)
        key_service_info = registry.get("key_service")
        if key_service_info and "port" in key_service_info:
            return f"http://127.0.0.1:{key_service_info['port']}"
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None

def _get_latest_fred_api_key() -> Optional[str]:
    """即時獲取 FRED API 金鑰，實現多源回退。"""
    key_service_url = _get_key_service_url()
    if key_service_url:
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{key_service_url}/api/keys/FRED_API_KEY/value")
                if response.status_code == 200:
                    api_key = response.json().get("key_value")
                    if api_key:
                        logger.info("從 key_service 獲取了 FRED API 金鑰。")
                        return api_key
        except httpx.RequestError:
            logger.warning("連接 key_service 失敗，回退到環境變數。")

    api_key = os.getenv("FRED_API_KEY")
    if api_key:
        logger.info("從環境變數中獲取了 FRED API 金鑰。")
    return api_key


# --- 資料庫操作函式 (原 db_utils.py) ---

def _save_series_to_db(series: pd.Series, ticker: str):
    """將時間序列數據儲存到 SQLite 資料庫。"""
    if series.empty:
        return
    if not DB_FILE.exists():
        logger.error(f"資料庫檔案不存在: {DB_FILE}。")
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        cursor = conn.cursor()
        data_to_insert = [
            (idx.strftime('%Y-%m-%d'), ticker, val)
            for idx, val in series.items() if pd.notna(val)
        ]
        if not data_to_insert:
            return

        sql = "INSERT OR REPLACE INTO time_series_data (date, ticker, price) VALUES (?, ?, ?)"
        cursor.executemany(sql, data_to_insert)
        conn.commit()
        logger.info(f"成功將 {len(data_to_insert)} 筆 '{ticker}' 數據儲存/更新至資料庫。")
    except sqlite3.Error as e:
        logger.error(f"儲存 '{ticker}' 數據時發生資料庫錯誤: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

def _load_series_from_db(ticker: str, start_date: str, end_date: str) -> Optional[pd.Series]:
    """從 SQLite 資料庫讀取時間序列數據。"""
    if not DB_FILE.exists():
        return None

    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        query = "SELECT date, price FROM time_series_data WHERE ticker = ? AND date BETWEEN ? AND ? ORDER BY date ASC"
        params = (ticker, start_date, end_date)
        df = pd.read_sql_query(query, conn, params=params, index_col='date', parse_dates=['date'])

        if df.empty:
            return None

        series = df['price']
        series.name = ticker
        logger.info(f"從資料庫快取中讀取 {len(series)} 筆 '{ticker}' 數據。")
        return series
    except (sqlite3.Error, pd.errors.DatabaseError) as e:
        logger.error(f"讀取 '{ticker}' 數據時發生資料庫錯誤: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


# --- 資料倉儲類別 ---

class DataRepository:
    """
    資料倉儲層的實現，封裝所有資料存取邏輯。
    這是與外部世界（資料庫、API）溝通的唯一介面。
    """
    def get_series(self, indicator_name: str, start_date: str, end_date: str, force_refresh: bool = False) -> Optional[pd.Series]:
        """
        獲取指定指標的時間序列數據，採用「快取優先」策略。
        """
        db_ticker = TICKER_MAP.get(indicator_name)
        if not db_ticker:
            logger.error(f"找不到指標 '{indicator_name}' 的 Ticker。")
            return None

        # 1. 嘗試從資料庫快取讀取
        if not force_refresh:
            cached_data = _load_series_from_db(db_ticker, start_date, end_date)
            if cached_data is not None and not cached_data.empty:
                cached_data.name = indicator_name
                return cached_data

        # 2. 從網路抓取
        logger.info(f"指標 '{indicator_name}' 在快取中未找到或被強制刷新，從網路抓取。")
        fetcher = FETCHER_MAP.get(indicator_name)
        if not fetcher:
            logger.error(f"找不到指標 '{indicator_name}' 的抓取器。")
            return None

        try:
            fetcher_args = {"start_date": start_date, "end_date": end_date}
            if "fred_" in fetcher.__module__ or "nyfed_" in fetcher.__module__:
                api_key = _get_latest_fred_api_key()
                if not api_key:
                    logger.error(f"無法為 '{indicator_name}' 獲取 API 金鑰。")
                    return None
                fetcher_args["api_key"] = api_key

            fresh_data = fetcher(**fetcher_args)

            if fresh_data is None or fresh_data.empty:
                logger.warning(f"抓取器為 '{indicator_name}' 返回了空資料。")
                return None

            # 3. 儲存到資料庫快取
            _save_series_to_db(fresh_data, db_ticker)

            fresh_data.name = indicator_name
            return fresh_data

        except Exception as e:
            logger.error(f"為 '{indicator_name}' 執行抓取器時發生錯誤: {e}", exc_info=True)
            return None

    def check_api_key_status(self) -> bool:
        """檢查 FRED API 金鑰是否有效。"""
        logger.info("正在檢查 API 金鑰狀態...")
        return _get_latest_fred_api_key() is not None