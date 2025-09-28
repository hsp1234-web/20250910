# -*- coding: utf-8 -*-
import os
from fredapi import Fred

def fetch_us_macro_data(fred_client):
    """
    使用 fredapi 函式庫獲取美國核心總體經濟指標。
    這是從 FRED 獲取官方數據的「基準」方法。

    :param fred_client: 已初始化的 Fred 客戶端實例。
    """
    print("--- 開始從 FRED 獲取美國核心總經指標 ---")

    # 美國核心總經指標的 FRED Series ID
    indicators_to_fetch = {
        'CPIAUCSL': '消費者物價指數 (CPI)',
        'GDPC1': '實質國內生產毛額 (Real GDP)',
        'UNRATE': '失業率',
        'PPIACO': '生產者物價指數 (PPI)',
        'PCE': '個人消費支出 (PCE)',
        'M2SL': 'M2 貨幣供給量',
        'DGS10': '10年期美債殖利率'
    }

    for symbol, description in indicators_to_fetch.items():
        try:
            # 獲取數據序列
            data_series = fred_client.get_series(symbol)

            # 移除所有 NaN (Not a Number) 的值並獲取最新數據
            latest_value = data_series.dropna().iloc[-1]
            latest_date = data_series.dropna().index[-1].strftime('%Y-%m-%d')

            print(f"\n✅ 成功獲取: {description} ({symbol})")
            print(f"  - 最新日期: {latest_date}")
            print(f"  - 最新數值: {latest_value}")

        except Exception as e:
            print(f"\n❌ 獲取 '{description}' ({symbol}) 時發生錯誤: {e}")

    print("\n--- FRED 指標獲取完畢 ---")

if __name__ == "__main__":
    try:
        # 從環境變數讀取 FRED API 金鑰
        api_key = os.getenv('FRED_API_KEY')
        if not api_key:
            raise ValueError("錯誤：請設定 FRED_API_KEY 環境變數。")

        # 初始化 Fred 客戶端
        fred = Fred(api_key=api_key)

        # 執行數據獲取
        fetch_us_macro_data(fred)

    except ValueError as e:
        print(e)
    except Exception as e:
        print(f"執行腳本時發生未預期的嚴重錯誤: {e}")