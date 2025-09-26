# services/bond_data_service/data_manager.py

import pandas as pd
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
    fred_wresbal_fetcher
)

class DataManager:
    def __init__(self, api_key: str):
        self.api_key = api_key
        # 擴充 fetcher_map 以包含所有新的指標
        self.fetcher_map = {
            "gdp": fred_gdp_fetcher.fetch_gdp_data,
            "cpi": fred_cpi_fetcher.fetch_cpi_data,
            "fedfunds": fred_fedfunds_fetcher.fetch_fedfunds_data,
            "dealer_positions": nyfed_positions_fetcher.fetch_nyfed_positions_data,
            "move_index": yahoo_finance_fetcher.fetch_move_index_data,
            "sofr": fred_sofr_fetcher.fetch_sofr_data,
            "dgs10": fred_dgs10_fetcher.fetch_dgs10_data,
            "dgs2": fred_dgs2_fetcher.fetch_dgs2_data,
            "rrp": fred_rrp_fetcher.fetch_rrp_data,
            "vix": fred_vix_fetcher.fetch_vix_data,
            "wresbal": fred_wresbal_fetcher.fetch_wresbal_data,
        }

    def save_series_to_db(self, series: pd.Series, indicator_name: str):
        """將 pandas Series 儲存到資料庫"""
        if series is None or series.empty:
            print(f"沒有可儲存的 '{indicator_name}' 數據。")
            return 0

        # 強制將索引轉換為 datetime 物件，並移除無效日期，增加穩健性
        series.index = pd.to_datetime(series.index, errors='coerce')
        series = series[series.index.notna()]

        if series.empty:
            print(f"警告：在日期轉換後，'{indicator_name}' 沒有剩下任何有效數據。")
            return 0

        conn = database.get_db_connection()
        cursor = conn.cursor()

        # 為了避免重複，我們先刪除該指標的所有舊數據
        # 更好的方法是使用 INSERT OR REPLACE，這裡為了簡單先用 DELETE
        print(f"正在清除 '{indicator_name}' 的舊數據...")
        cursor.execute("DELETE FROM macro_data WHERE indicator = ?", (indicator_name,))

        print(f"正在將 {len(series)} 筆 '{indicator_name}' 新數據寫入資料庫...")
        rows_to_insert = []

        # 將 Series 轉換為 DataFrame 並迭代，這是更穩健的作法
        df_to_insert = series.reset_index()
        df_to_insert.columns = ['date', 'value'] # 明確命名欄位

        for _, row in df_to_insert.iterrows():
            date_obj = row['date']  # 這確保了我們處理的是 Timestamp 物件
            value = row['value']
            # 將 pandas 的 Timestamp 轉換為 'YYYY-MM-DD' 格式的字串
            date_str = date_obj.strftime('%Y-%m-%d')
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
            # raise ValueError(f"找不到指標 '{indicator_name}' 的抓取器。")
            # --- 修改：找不到抓取器時，不再拋出錯誤，而是記錄警告並返回 ---
            print(f"警告：在 data_manager 中找不到指標 '{indicator_name}' 的抓取器。將跳過此指標的抓取。")
            logger.warning(f"在 data_manager 中找不到指標 '{indicator_name}' 的抓取器。")
            return 0

        print(f"正在為指標 '{indicator_name}' 執行抓取...")
        # 確保 fetcher 函式被正確呼叫
        try:
            series_data = fetcher(self.api_key)
        except Exception as e:
            print(f"錯誤：執行指標 '{indicator_name}' 的抓取器時發生錯誤: {e}")
            logger.error(f"執行指標 '{indicator_name}' 的抓取器時出錯: {e}", exc_info=True)
            return 0

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
