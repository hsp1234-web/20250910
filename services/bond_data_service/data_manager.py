# services/bond_data_service/data_manager.py

import pandas as pd
import logging
import database
# 匯入所有資料抓取器
from data_fetchers import (
    fred_gdp_fetcher,
    fred_cpi_fetcher,
    fred_fedfunds_fetcher,
    nyfed_positions_fetcher,
    yahoo_finance_fetcher,
    fred_sofr_fetcher,
    fred_dgs10_fetcher,
    fred_dgs2_fetcher,
    fred_rrp_fetcher,
    fred_vix_fetcher,
    fred_wresbal_fetcher,
    fred_hys_fetcher
)

logger = logging.getLogger(__name__)

class DataManager:
    """負責管理所有宏觀經濟數據的抓取、儲存與讀取。"""
    def __init__(self, api_key: str):
        self.api_key = api_key
        # 將所有指標的抓取函式映射到其名稱
        self.fetcher_map = {
            "gdp": fred_gdp_fetcher.fetch_gdp_data,
            "cpi": fred_cpi_fetcher.fetch_cpi_data,
            "fedfunds": fred_fedfunds_fetcher.fetch_fedfunds_data,
            "dealer_positions": nyfed_positions_fetcher.fetch_nyfed_total_positions_data,
            "dealer_positions_short": nyfed_positions_fetcher.fetch_nyfed_short_term_positions_data,
            "dealer_positions_long": nyfed_positions_fetcher.fetch_nyfed_long_term_positions_data,
            "move_index": yahoo_finance_fetcher.fetch_move_index_data,
            "sofr": fred_sofr_fetcher.fetch_sofr_data,
            "dgs10": fred_dgs10_fetcher.fetch_dgs10_data,
            "dgs2": fred_dgs2_fetcher.fetch_dgs2_data,
            "rrp": fred_rrp_fetcher.fetch_rrp_data,
            "vix": fred_vix_fetcher.fetch_vix_data,
            "wresbal": fred_wresbal_fetcher.fetch_wresbal_data,
            "us_high_yield_spread": fred_hys_fetcher.fetch_hys_data,
        }

    def save_series_to_db(self, series: pd.Series, indicator_name: str) -> int:
        """將 pandas Series 儲存到資料庫，並進行資料清理。"""
        if series is None or series.empty:
            logger.info(f"指標 '{indicator_name}' 沒有需要儲存的新數據。")
            return 0

        # 強制將索引轉換為 datetime 物件，並移除無效日期，增加穩健性
        series.index = pd.to_datetime(series.index, errors='coerce')
        series = series.dropna()
        series = series[series.index.notna()]

        if series.empty:
            logger.warning(f"指標 '{indicator_name}' 在清理後沒有剩下任何有效數據。")
            return 0

        conn = database.get_db_connection()
        cursor = conn.cursor()

        logger.info(f"正在為指標 '{indicator_name}' 清除舊數據...")
        cursor.execute("DELETE FROM macro_data WHERE indicator = ?", (indicator_name,))

        logger.info(f"正在將 {len(series)} 筆 '{indicator_name}' 新數據寫入資料庫...")
        df_to_insert = series.reset_index()
        df_to_insert.columns = ['date', 'value']

        rows_to_insert = [
            (indicator_name, row['date'].strftime('%Y-%m-%d'), float(row['value']))
            for _, row in df_to_insert.iterrows()
        ]

        cursor.executemany(
            "INSERT INTO macro_data (indicator, date, value) VALUES (?, ?, ?)",
            rows_to_insert
        )

        conn.commit()
        conn.close()
        logger.info(f"✅ 成功儲存 {len(rows_to_insert)} 筆 '{indicator_name}' 數據。")
        return len(rows_to_insert)

    def fetch_and_store_data(self, indicator_name: str) -> int:
        """根據指標名稱，觸發對應的抓取器並儲存數據。"""
        fetcher = self.fetcher_map.get(indicator_name.lower())
        if not fetcher:
            logger.warning(f"在 DataManager 中找不到指標 '{indicator_name}' 的抓取器，將跳過。")
            return 0

        logger.info(f"正在為指標 '{indicator_name}' 執行資料抓取...")
        try:
            # 某些抓取器（如 FRED 的）需要 API 金鑰
            if "fred" in fetcher.__module__:
                series_data = fetcher(self.api_key)
            else:
                series_data = fetcher()
        except Exception as e:
            logger.error(f"執行指標 '{indicator_name}' 的抓取器時發生錯誤: {e}", exc_info=True)
            return 0

        if series_data is not None:
            return self.save_series_to_db(series_data, indicator_name)
        return 0

    def get_data(self, indicator_name: str) -> list[dict]:
        """從資料庫中獲取指定指標的數據，以供圖表使用。"""
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT date, value FROM macro_data WHERE indicator = ? ORDER BY date ASC",
            (indicator_name,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"date": row["date"], "value": row["value"]} for row in rows]
