# -*- coding: utf-8 -*-
import os
import pandas as pd
from fredapi import Fred

def get_fred_client():
    """
    初始化並返回一個 Fred 客戶端實例。
    從環境變數 `FRED_API_KEY` 讀取 API 金鑰。
    """
    api_key = os.getenv('FRED_API_KEY', 'YOUR_FRED_API_KEY')
    if not api_key or api_key == 'YOUR_FRED_API_KEY':
        raise ValueError("請設定 FRED_API_KEY 環境變數或在腳本中直接提供您的 API 金鑰。")
    return Fred(api_key=api_key)

def print_latest_data(fred_client, series_id, description):
    """
    通用函數，用於獲取並打印指定 FRED 系列的最新數據。
    """
    try:
        data = fred_client.get_series(series_id)
        last_valid_data = data.dropna().iloc[-1]
        last_valid_date = data.dropna().index[-1].strftime('%Y-%m-%d')
        print(f"\n成功獲取: {description} ({series_id})")
        print(f"  - 最新日期: {last_valid_date}")
        print(f"  - 最新數值: {last_valid_data}")
    except Exception as e:
        print(f"\n獲取 {series_id} 時發生錯誤: {e}")

def fetch_financial_stress_data(fred_client):
    """獲取金融壓力相關指標。"""
    print("--- (1/2) 開始從 FRED 獲取金融壓力指標 ---")
    series_ids = {
        'STLFSI4': '聖路易聯準會金融壓力指數 (週)',
        'H0RESPPALDDXAWNWW': '一級交易商信貸工具資產 (週)',
        'T10Y3M': '10年期與3個月期公債利差 (日)',
        'TEDRATE': 'TED 利差 (日)'
    }
    for series_id, description in series_ids.items():
        print_latest_data(fred_client, series_id, description)
    print("\n--- 金融壓力指標獲取完畢 ---")

def fetch_macroeconomic_data(fred_client):
    """獲取核心總體經濟指標。"""
    print("\n--- (2/2) 開始從 FRED 獲取總體經濟指標 ---")
    series_ids = {
        'CPIAUCSL': '消費者物價指數 (CPI)',
        'UNRATE': '失業率',
        'GDPC1': '實質國內生產毛額 (Real GDP)',
        'PPIACO': '生產者物價指數 (PPI)',
        'UMCSENT': '密西根大學消費者信心指數'
    }
    for series_id, description in series_ids.items():
        print_latest_data(fred_client, series_id, description)
    print("\n--- 總體經濟指標獲取完畢 ---")


if __name__ == "__main__":
    try:
        fred = get_fred_client()
        fetch_financial_stress_data(fred)
        fetch_macroeconomic_data(fred)
    except ValueError as e:
        print(e)
    except Exception as e:
        print(f"執行腳本時發生未預期的錯誤: {e}")