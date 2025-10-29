# services/bond_data_service/repository.py
import logging
import sqlite3
from pathlib import Path
from typing import Dict, Optional
import pandas as pd
import httpx
import json

logger = logging.getLogger(__name__)

# --- 資料庫設定 ---
DB_FILE = Path(__file__).resolve().parent / "bond_data.sqlite3"
SERVICE_REGISTRY_FILE = Path("/tmp/service_registry.json")

def initialize_database():
    """初始化資料庫，確保資料表存在。"""
    logger.info("分析服務：正在檢查並初始化資料庫...")
    try:
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS time_series_data (
                date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                price REAL NOT NULL,
                PRIMARY KEY (date, ticker)
            )""")
            conn.commit()
        logger.info(f"✅ 分析服務：資料庫初始化完成，檔案位於: {DB_FILE}")
    except Exception as e:
        logger.error(f"❌ 分析服務：資料庫初始化失敗: {e}", exc_info=True)
        raise

async def get_fetcher_service_url() -> Optional[str]:
    """從服務註冊中心異步獲取 bond_fetcher_service 的基礎 URL。"""
    if not SERVICE_REGISTRY_FILE.exists():
        logger.error("服務註冊中心檔案不存在。")
        return None
    try:
        with open(SERVICE_REGISTRY_FILE, 'r') as f:
            registry = json.load(f)
        service_info = registry.get('bond_fetcher_service')
        if not service_info or not service_info.get('port'):
            logger.error("在註冊中心找不到 'bond_fetcher_service'。")
            return None
        port = service_info['port']
        return f"http://127.0.0.1:{port}"
    except Exception as e:
        logger.error(f"讀取服務註冊中心時出錯: {e}")
        return None

class FinancialDataRepository:
    """
    重構後的倉儲，職責單一化：
    1. 從本地快取（資料庫）讀取資料。
    2. 如果快取未命中，委託 bond_fetcher_service 進行資料抓取。
    """
    def __init__(self):
        self._ticker_map: Dict[str, str] = {
            "sofr": "SOFR", "vix": "VIXCLS", "dgs10": "DGS10", "dgs2": "DGS2",
            "us_high_yield_spread": "HYG", "dealer_net_positions": "NYFED_TOTAL_POS",
            "dealer_long_term_positions": "NYFED_LONG_POS", "dealer_short_term_positions": "NYFED_SHORT_POS",
            "rrp": "RRPONTSYD", "wresbal": "WRESBAL",
        }
        # 增加一個 client session 以提高效能
        self.client = httpx.AsyncClient(timeout=10.0)

    async def _trigger_fetcher_service(self, indicators: list[str], start_date: str, end_date: str):
        """向 bond_fetcher_service 發送一個非同步請求來觸發資料抓取。"""
        fetcher_url = await get_fetcher_service_url()
        if not fetcher_url:
            logger.error("無法觸發抓取，因為找不到抓取器服務的 URL。")
            return

        request_body = {
            "indicators": indicators,
            "start_date": start_date,
            "end_date": end_date
        }
        try:
            logger.info(f"正在向抓取器服務 ({fetcher_url}/api/fetch) 發送請求...")
            response = await self.client.post(f"{fetcher_url}/api/fetch", json=request_body)
            response.raise_for_status()
            logger.info(f"成功觸發抓取器服務為 {indicators} 更新資料。")
        except httpx.RequestError as e:
            logger.error(f"請求抓取器服務時發生網路錯誤: {e}", exc_info=True)
        except httpx.HTTPStatusError as e:
            logger.error(f"抓取器服務返回錯誤狀態: {e.response.status_code} - {e.response.text}", exc_info=True)

    def _load_series_from_db(self, ticker: str, start_date: str, end_date: str) -> Optional[pd.Series]:
        """從 SQLite 資料庫讀取時間序列數據。"""
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
        except Exception as e:
            logger.error(f"讀取 '{ticker}' 數據時發生資料庫錯誤: {e}", exc_info=True)
            return None

    async def get_series(self, indicator_name: str, start_date: str, end_date: str) -> Optional[pd.Series]:
        """
        獲取指定指標的時間序列數據。
        如果快取未命中，將非同步觸發抓取服務並返回 None。
        """
        db_ticker = self._ticker_map.get(indicator_name)
        if not db_ticker:
            logger.error(f"找不到指標 '{indicator_name}' 對應的 Ticker。")
            return None

        # 1. 嘗試從快取讀取
        cached_data = self._load_series_from_db(db_ticker, start_date, end_date)
        if cached_data is not None:
            cached_data.name = indicator_name
            return cached_data

        # 2. 快取未命中：觸發背景抓取並返回 None
        logger.info(f"'{indicator_name}' 在快取中未命中。將觸發背景抓取。")
        await self._trigger_fetcher_service([indicator_name], start_date, end_date)
        return None # 返回 None 表示資料正在準備中

    async def get_all_series(self, start_date: str, end_date: str) -> (Dict[str, pd.Series], bool):
        """
        獲取所有指標的數據。
        返回一個包含已快取數據的字典，以及一個布林值表示是否所有數據都已命中快取。
        """
        all_cached_data = {}
        missing_indicators = []

        for indicator_name in self._ticker_map.keys():
            series = await self.get_series(indicator_name, start_date, end_date)
            if series is not None:
                all_cached_data[indicator_name] = series
            else:
                # get_series 內部已經觸發了單個指標的抓取
                missing_indicators.append(indicator_name)

        all_hit = not bool(missing_indicators)
        return all_cached_data, all_hit
