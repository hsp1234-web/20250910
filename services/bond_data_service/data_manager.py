# services/bond_data_service/data_manager.py

import pandas as pd
from . import database
from .data_fetchers import fred_gdp_fetcher, fred_cpi_fetcher, fred_fedfunds_fetcher

class DataManager:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.fetcher_map = {
            "gdp": fred_gdp_fetcher.fetch_gdp_data,
            "cpi": fred_cpi_fetcher.fetch_cpi_data,
            "fedfunds": fred_fedfunds_fetcher.fetch_fedfunds_data,
        }

    def save_series_to_db(self, series: pd.Series, indicator_name: str):
        """將 pandas Series 儲存到資料庫"""
        if series is None or series.empty:
            print(f"沒有可儲存的 '{indicator_name}' 數據。")
            return 0

        conn = database.get_db_connection()
        cursor = conn.cursor()

        # 為了避免重複，我們先刪除該指標的所有舊數據
        # 更好的方法是使用 INSERT OR REPLACE，這裡為了簡單先用 DELETE
        print(f"正在清除 '{indicator_name}' 的舊數據...")
        cursor.execute("DELETE FROM macro_data WHERE indicator = ?", (indicator_name,))

        print(f"正在將 {len(series)} 筆 '{indicator_name}' 新數據寫入資料庫...")
        rows_to_insert = []
        for date, value in series.items():
            # 將 pandas 的 Timestamp 轉換為 'YYYY-MM-DD' 格式的字串
            date_str = date.strftime('%Y-%m-%d')
            rows_to_insert.append((indicator_name, date_str, float(value)))

        cursor.executemany(
            "INSERT INTO macro_data (indicator, date, value) VALUES (?, ?, ?)",
            rows_to_insert
        )

        conn.commit()
        conn.close()
        print(f"✅ 成功儲存 {len(rows_to_insert)} 筆 '{indicator_name}' 數據。")
        return len(rows_to_insert)

    def fetch_and_store_data(self, indicator_name: str):
        """根據指標名稱，觸發對應的抓取器並儲存數據。"""
        fetcher = self.fetcher_map.get(indicator_name.lower())
        if not fetcher:
            raise ValueError(f"找不到指標 '{indicator_name}' 的抓取器。")

        print(f"正在為指標 '{indicator_name}' 執行抓取...")
        series_data = fetcher(self.api_key)

        if series_data is not None:
            return self.save_series_to_db(series_data, indicator_name)
        return 0

    def get_data(self, indicator_name: str):
        """從資料庫中獲取指定指標的數據。"""
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT date, value FROM macro_data WHERE indicator = ? ORDER BY date ASC",
            (indicator_name,)
        )
        rows = cursor.fetchall()
        conn.close()
        # 將結果轉換為適合圖表庫的格式
        return [{"date": row["date"], "value": row["value"]} for row in rows]
