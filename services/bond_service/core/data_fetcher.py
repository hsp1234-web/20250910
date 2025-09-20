# -*- coding: utf-8 -*-
"""
數據獲取模組 (Data Fetcher)

功能：
- 從 FRED、Yahoo Finance 和 NY Fed API 獲取所有需要的原始數據。
- 清理、處理並合併所有數據源，為後續計算準備一個統一的 DataFrame。
- 此模組的邏輯主要移植自 `一級交易pro.py` 的 Cell 4, 5, 6, 7。
"""

import logging
import io
import time
import pandas as pd
import numpy as np
import requests
import yfinance as yf
from fredapi import Fred
from datetime import datetime

# 從設定檔導入專案設定
from services.bond_service.config import PROJECT_CONFIG

# 設定日誌
logger = logging.getLogger(__name__)


def fetch_fred_data(fred_api: Fred, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    """
    從 FRED 獲取經濟數據 (移植自 Cell 4)。

    Args:
        fred_api (Fred): 已初始化的 fredapi 物件。
        start_dt (datetime): 數據獲取的開始日期。
        end_dt (datetime): 數據獲取的結束日期。

    Returns:
        pd.DataFrame: 包含所有 FRED 數據的 DataFrame，索引為業務日。
    """
    logger.info(f"開始從 FRED 獲取數據，範圍：{start_dt.date()} 到 {end_dt.date()}。")
    fred_series_map = {
        'SOFR': 'SOFR',
        'DGS10': 'DGS10',
        'DGS2': 'DGS2',
        'RRP': 'RRPONTSYD',
        'VIX': 'VIXCLS',
        'Reserves': 'WRESBAL'
    }

    data_fred_temp = pd.DataFrame()
    daily_index_for_fred = pd.date_range(start=start_dt, end=end_dt, freq='D')

    for name, series_id in fred_series_map.items():
        try:
            logger.debug(f"正在抓取 FRED 序列: {name} ({series_id})")
            s = fred_api.get_series(series_id, start_dt, end_dt)
            s.index = pd.to_datetime(s.index).tz_localize(None)

            if s.empty or s.isna().all():
                logger.warning(f"FRED 序列 '{name}' ({series_id}) 返回數據為空。")
                data_fred_temp[name] = pd.Series(dtype='float64')
                continue

            freq_str = pd.infer_freq(s.index)
            # 對非日頻數據（如週頻）進行向前填充
            if (freq_str and ('W' in freq_str.upper() or 'M' in freq_str.upper())) or not s.index.is_monotonic_increasing:
                s = s.sort_index()
                s_aligned = s.reindex(daily_index_for_fred).ffill()
            else:
                s_aligned = s.reindex(daily_index_for_fred, method='ffill')

            data_fred_temp[name] = s_aligned
            logger.debug(f"成功處理 FRED 序列: {name}")

        except Exception as e:
            logger.error(f"處理 FRED 序列 '{name}' ({series_id}) 時出錯: {e}", exc_info=True)
            data_fred_temp[name] = pd.Series(dtype='float64')

    # 對齊到業務日索引
    if not data_fred_temp.empty:
        business_day_index = pd.date_range(start=start_dt, end=end_dt, freq='B')
        fred_data_df = data_fred_temp.reindex(business_day_index)
        logger.info(f"FRED 數據已成功獲取並對齊至 {len(fred_data_df)} 個業務日。")
        return fred_data_df
    else:
        logger.warning("未能從 FRED 獲取任何數據。")
        return pd.DataFrame()


def fetch_yahoo_data(start_dt: datetime, end_dt: datetime, config: dict) -> pd.DataFrame:
    """
    從 Yahoo Finance 獲取額外市場數據 (移植自 Cell 5)。

    Args:
        start_dt (datetime): 數據獲取的開始日期。
        end_dt (datetime): 數據獲取的結束日期。
        config (dict): 專案設定字典。

    Returns:
        pd.DataFrame: 包含 MOVE 指數和 (可選的) ETF 數據的 DataFrame。
    """
    logger.info(f"開始從 Yahoo Finance 獲取數據，範圍：{start_dt.date()} 到 {end_dt.date()}。")
    start_str = start_dt.strftime('%Y-%m-%d')
    end_str = end_dt.strftime('%Y-%m-%d')

    # 創建業務日索引的基礎 DataFrame
    business_day_index = pd.date_range(start=start_dt, end=end_dt, freq='B')
    yahoo_data_df = pd.DataFrame(index=business_day_index)

    # 1. 抓取 MOVE 指數
    try:
        move_ticker = yf.Ticker('^MOVE')
        move_data = move_ticker.history(start=start_str, end=end_str)
        if not move_data.empty and 'Close' in move_data.columns:
            move_series = pd.to_numeric(move_data['Close'], errors='coerce').dropna()
            move_series.index = pd.to_datetime(move_series.index).tz_localize(None)
            yahoo_data_df['MOVE_Close'] = move_series.reindex(business_day_index, method='ffill')
            logger.debug("成功獲取 ^MOVE 指數數據。")
    except Exception as e:
        logger.error(f"抓取 MOVE 指數時出錯: {e}", exc_info=True)

    # 2. 抓取長債 ETF (可選)
    enable_etf = config.get('enable_lt_bond_etf_plot', False)
    etf_ticker_str = config.get('lt_bond_etf_ticker', '').strip().upper()

    if enable_etf and etf_ticker_str:
        etf_col_name = f'ETF_{etf_ticker_str}_Price'
        try:
            etf_ticker = yf.Ticker(etf_ticker_str)
            etf_data = etf_ticker.history(start=start_str, end=end_str)
            if not etf_data.empty and 'Close' in etf_data.columns:
                etf_series = pd.to_numeric(etf_data['Close'], errors='coerce').dropna()
                etf_series.index = pd.to_datetime(etf_series.index).tz_localize(None)
                yahoo_data_df[etf_col_name] = etf_series.reindex(business_day_index, method='ffill')
                logger.debug(f"成功獲取 ETF {etf_ticker_str} 數據。")
        except Exception as e:
            logger.error(f"抓取 ETF {etf_ticker_str} 時出錯: {e}", exc_info=True)

    logger.info(f"Yahoo Finance 數據獲取完成，共 {len(yahoo_data_df)} 行。")
    return yahoo_data_df


def fetch_nyfed_data(config: dict) -> pd.Series:
    """
    從紐約聯儲網站抓取並處理一級交易商持有量數據 (移植自 Cell 6)。

    Args:
        config (dict): 專案設定字典。

    Returns:
        pd.Series: 包含合併和清理後的一級交易商持有量時間序列。
    """
    logger.info("開始從 NY Fed 獲取和處理持有量數據。")
    ny_fed_urls = config.get('ny_fed_positions_urls', [])
    if not ny_fed_urls:
        logger.error("設定檔中未找到 'ny_fed_positions_urls'。")
        return pd.Series(dtype='float64')

    all_positions_data = []
    with requests.Session() as session:
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        for url in ny_fed_urls:
            file_source_name = url.split('/')[-3]
            logger.debug(f"正在處理文件: {file_source_name} 從 {url}")
            try:
                response = session.get(url, timeout=120)
                response.raise_for_status()
                excel_content = io.BytesIO(response.content)

                # 自動檢測表頭
                header_row = None
                possible_headers = [3, 4, 0]
                df_long = None
                for h in possible_headers:
                    try:
                        df_peek = pd.read_excel(excel_content, header=h, nrows=5, engine='openpyxl')
                        excel_content.seek(0)
                        cols_lower = [str(c).lower() for c in df_peek.columns]
                        if 'time series' in cols_lower and ('value' in cols_lower or 'value (millions)' in cols_lower):
                            header_row = h
                            df_long = pd.read_excel(excel_content, header=header_row, parse_dates=True, engine='openpyxl')
                            break
                    except Exception:
                        excel_content.seek(0)
                        continue

                if df_long is None:
                    logger.warning(f"文件 {file_source_name}: 無法自動檢測有效的表頭。跳過此文件。")
                    continue

                # 清理與轉換
                date_col = df_long.columns[0]
                df_long.rename(columns={date_col: 'Date'}, inplace=True)
                df_long['Date'] = pd.to_datetime(df_long['Date'], errors='coerce')
                df_long.dropna(subset=['Date'], inplace=True)
                df_long.set_index('Date', inplace=True)

                actual_ts_col = next((c for c in df_long.columns if 'time series' in str(c).lower()), None)
                actual_val_col = next((c for c in df_long.columns if 'value' in str(c).lower()), None)

                if not actual_ts_col or not actual_val_col:
                    logger.warning(f"文件 {file_source_name}: 缺少 'Time Series' 或 'Value' 欄位。跳過。")
                    continue

                df_long[actual_val_col] = pd.to_numeric(df_long[actual_val_col], errors='coerce')
                df_long.dropna(subset=[actual_val_col, actual_ts_col], inplace=True)

                df_wide = df_long.pivot_table(index=df_long.index, columns=actual_ts_col, values=actual_val_col)

                # 根據規則加總
                target_cols = []
                if 'SBN' in url:
                    target_cols = [c for c in df_wide.columns if isinstance(c, str) and c.startswith('PDPOSGSC-')]
                elif 'SBP2013' in url:
                    target_cols = config.get('sbp2013_cols_to_sum', [])
                elif 'SBP2001' in url:
                    target_cols = config.get('sbp2001_cols_to_sum', [])

                cols_to_sum = [c for c in target_cols if c in df_wide.columns]
                if not cols_to_sum:
                    logger.warning(f"文件 {file_source_name}: 未找到任何預期的目標欄位進行加總。")
                    continue

                daily_total = df_wide[cols_to_sum].sum(axis=1, skipna=True)
                daily_total = daily_total.dropna()[daily_total != 0]

                if not daily_total.empty:
                    all_positions_data.append(daily_total)
                    logger.debug(f"成功處理文件 {file_source_name}，獲得 {len(daily_total)} 筆數據。")

            except requests.RequestException as e:
                logger.error(f"下載 NY Fed 文件 {file_source_name} 失敗: {e}")
            except Exception as e:
                logger.error(f"處理 NY Fed 文件 {file_source_name} 時發生未預期錯誤: {e}", exc_info=True)

    if not all_positions_data:
        logger.warning("未能從 NY Fed 成功處理任何持有量數據。")
        return pd.Series(dtype='float64')

    # 合併所有數據並處理重疊
    combined_series = pd.concat(all_positions_data).sort_index()
    final_series = combined_series.groupby(level=0).last()
    final_series.name = 'Total_Gross_Positions_Millions'
    logger.info(f"NY Fed 持有量數據合併完成，共 {len(final_series)} 筆有效數據。")

    return final_series


def get_merged_data(start_date_str: str, end_date_str: str) -> pd.DataFrame:
    """
    執行所有數據獲取步驟並將其合併為一個 DataFrame (移植自 Cell 7)。

    Args:
        start_date_str (str): 開始日期 (YYYY-MM-DD)。
        end_date_str (str): 結束日期 (YYYY-MM-DD)。

    Returns:
        pd.DataFrame: 包含所有來源數據的最終合併 DataFrame。
    """
    logger.info(f"開始完整數據獲取與合併流程，範圍：{start_date_str} 到 {end_date_str}。")
    start_dt = pd.to_datetime(start_date_str)
    end_dt = pd.to_datetime(end_date_str)

    # 1. 初始化 FRED API
    api_key = PROJECT_CONFIG.get('fred_api_key')
    if not api_key:
        logger.critical("設定檔中缺少 FRED API 金鑰。")
        raise ValueError("FRED API 金鑰未設定。")
    fred_api = Fred(api_key=api_key)

    # 2. 獲取各數據源數據
    fred_df = fetch_fred_data(fred_api, start_dt, end_dt)
    yahoo_df = fetch_yahoo_data(start_dt, end_dt, PROJECT_CONFIG)
    nyfed_series = fetch_nyfed_data(PROJECT_CONFIG)

    # 3. 合併數據
    # 以 FRED 數據為基礎 (它已經有業務日索引)
    merged_df = fred_df.copy()

    # 合併 Yahoo Finance 數據
    if not yahoo_df.empty:
        merged_df = pd.merge(merged_df, yahoo_df, left_index=True, right_index=True, how='left')

    # 合併 NY Fed 數據
    if not nyfed_series.empty:
        merged_df = pd.merge(merged_df, nyfed_series.to_frame(), left_index=True, right_index=True, how='left')
        # 向前填充 NY Fed 的週頻數據
        if 'Total_Gross_Positions_Millions' in merged_df.columns:
            merged_df['Total_Gross_Positions_Millions'] = merged_df['Total_Gross_Positions_Millions'].ffill()

    # 4. 欄位清理與重命名
    if 'RRP' in merged_df.columns:
        merged_df.rename(columns={'RRP': 'RRP_Amount_Billions'}, inplace=True)
    if 'MOVE_Close' in merged_df.columns:
        merged_df.rename(columns={'MOVE_Close': 'Volatility_Index'}, inplace=True)

    # 確保所有預期欄位都存在
    expected_cols = [
        'SOFR', 'DGS10', 'DGS2', 'RRP_Amount_Billions', 'VIX', 'Reserves',
        'Volatility_Index', 'Total_Gross_Positions_Millions'
    ]
    etf_ticker_final = PROJECT_CONFIG.get('lt_bond_etf_ticker', '').strip().upper()
    if etf_ticker_final:
        expected_cols.append(f'ETF_{etf_ticker_final}_Price')

    for col in expected_cols:
        if col not in merged_df.columns:
            merged_df[col] = np.nan

    logger.info(f"所有數據源合併完成。最終 DataFrame 維度: {merged_df.shape}")

    return merged_df
