# services/bond_data_service/data_fetchers/nyfed_positions_fetcher.py
import pandas as pd
import requests
import io
import logging
from typing import List, Literal, Optional
from ..db_utils import save_series_to_db

# --- 常數 ---
NY_FED_URLS = [
    "https://markets.newyorkfed.org/api/pd/get/SBN2024/timeseries/PDPOSGSC-L2_PDPOSGSC-G2L3_PDPOSGSC-G3L6_PDPOSGSC-G6L7_PDPOSGSC-G7L11_PDPOSGSC-G11L21_PDPOSGSC-G21.xlsx",
    "https://markets.newyorkfed.org/api/pd/get/SBN2022/timeseries/PDPOSGSC-L2_PDPOSGSC-G2L3_PDPOSGSC-G3L6_PDPOSGSC-G6L7_PDPOSGSC-G7L11_PDPOSGSC-G11L21_PDPOSGSC-G21.xlsx",
    "https://markets.newyorkfed.org/api/pd/get/SBN2015/timeseries/PDPOSGSC-L2_PDPOSGSC-G2L3_PDPOSGSC-G3L6_PDPOSGSC-G6L7_PDPOSGSC-G7L11_PDPOSGSC-G11.xlsx",
    "https://markets.newyorkfed.org/api/pd/get/SBN2013/timeseries/PDPOSGSC-L2_PDPOSGSC-G2L3_PDPOSGSC-G3L6_PDPOSGSC-G6L7_PDPOSGSC-G7L11_PDPOSGSC-G11.xlsx",
    "https://markets.newyorkfed.org/api/pd/get/SBP2013/timeseries/PDPUSGCS3LNOP_PDPUSGCS36NOP_PDPUSGCS611NOP_PDPUSGCSM11NOP.xlsx",
    "https://markets.newyorkfed.org/api/pd/get/SBP2001/timeseries/PDPUSGCS5LNOP_PDPUSGCS5MNOP.xlsx"
]

# 定義不同期限的欄位
SBN_SHORT_TERM_COLS = ['PDPOSGSC-L2', 'PDPOSGSC-G2L3']
SBP2013_SHORT_TERM_COLS = ['PDPUSGCS3LNOP']
SBP2001_SHORT_TERM_COLS = ['PDPUSGCS5LNOP']
SBN_LONG_TERM_COLS = ['PDPOSGSC-G7L11', 'PDPOSGSC-G11L21', 'PDPOSGSC-G21', 'PDPOSGSC-G11']
SBP2013_LONG_TERM_COLS = ['PDPUSGCS611NOP', 'PDPUSGCSM11NOP']
SBP2001_LONG_TERM_COLS = ['PDPUSGCS5MNOP']

logger = logging.getLogger(__name__)

def _find_header_row(excel_content: io.BytesIO, max_rows_to_scan: int = 10) -> Optional[int]:
    """
    動態掃描 Excel 檔案以尋找表頭所在的行。

    Args:
        excel_content (io.BytesIO): Excel 檔案的二進位內容。
        max_rows_to_scan (int): 要掃描的最大行數。

    Returns:
        Optional[int]: 表頭所在的行號（從 0 開始），如果找不到則返回 None。
    """
    try:
        df_peek = pd.read_excel(excel_content, header=None, nrows=max_rows_to_scan, engine='openpyxl')
        excel_content.seek(0)  # 重置指標供後續使用
        for i, row in df_peek.iterrows():
            # 檢查行中的值是否包含關鍵字
            row_values = [str(v).lower() for v in row.values]
            if any("effective date" in v for v in row_values) or any("time series" in v for v in row_values):
                logger.info(f"在第 {i} 行找到表頭關鍵字。")
                return i
    except Exception as e:
        logger.error(f"掃描表頭時發生錯誤: {e}")
        excel_content.seek(0)
    return None

def _fetch_and_process_files(maturity: Literal['total', 'short', 'long'], start_date: str, end_date: str) -> pd.Series:
    db_ticker = f"NYFED_{maturity.upper()}_POS"
    series_name = f'dealer_positions_{maturity}'

    logger.info(f"開始為 '{series_name}' 從 NY Fed 抓取數據...")
    all_positions_data = []

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })

    for url in NY_FED_URLS:
        file_source_name = url.split('/')[-3] if len(url.split('/')) > 2 else url.split('/')[-1]
        logger.info(f"正在為 '{series_name}' 處理文件: {file_source_name}")

        try:
            response = session.get(url, timeout=120)
            response.raise_for_status()
            excel_content = io.BytesIO(response.content)

            header_row = _find_header_row(excel_content)

            if header_row is None:
                logger.warning(f"文件 {file_source_name}: 未能動態找到有效表頭，跳過。")
                continue

            # 使用找到的表頭行來解析整個檔案
            df_long = pd.read_excel(excel_content, header=header_row, engine='openpyxl')

            # --- 後續處理邏輯 ---
            # 尋找日期欄和數值欄
            date_col = next((c for c in df_long.columns if "date" in str(c).lower()), df_long.columns[0])
            ts_col = next((c for c in df_long.columns if "time series" in str(c).lower()), None)
            val_col = next((c for c in df_long.columns if "value" in str(c).lower()), None)

            if not ts_col or not val_col:
                logger.warning(f"文件 {file_source_name}: 缺少 'Time Series' 或 'Value' 欄位，跳過。")
                continue

            df_long.rename(columns={date_col: 'date', ts_col: 'series_id', val_col: 'value'}, inplace=True)

            df_long['date'] = pd.to_datetime(df_long['date'], errors='coerce')
            df_long.dropna(subset=['date'], inplace=True)
            df_long['value'] = pd.to_numeric(df_long['value'], errors='coerce')
            df_long.dropna(subset=['value', 'series_id'], inplace=True)

            if df_long.empty: continue

            df_wide = pd.pivot_table(df_long, index='date', columns='series_id', values='value')

            target_cols: List[str] = []
            if 'SBN' in url:
                if maturity == 'total': target_cols = [c for c in df_wide.columns if isinstance(c, str) and c.startswith('PDPOSGSC-')]
                elif maturity == 'short': target_cols = SBN_SHORT_TERM_COLS
                elif maturity == 'long': target_cols = SBN_LONG_TERM_COLS
            elif 'SBP2013' in url:
                if maturity == 'total': target_cols = SBP2013_SHORT_TERM_COLS + SBP2013_LONG_TERM_COLS
                elif maturity == 'short': target_cols = SBP2013_SHORT_TERM_COLS
                elif maturity == 'long': target_cols = SBP2013_LONG_TERM_COLS
            elif 'SBP2001' in url:
                if maturity == 'total': target_cols = SBP2001_SHORT_TERM_COLS + SBP2001_LONG_TERM_COLS
                elif maturity == 'short': target_cols = SBP2001_SHORT_TERM_COLS
                elif maturity == 'long': target_cols = SBP2001_LONG_TERM_COLS

            cols_to_sum = [c for c in target_cols if c in df_wide.columns]
            if not cols_to_sum: continue

            daily_total = df_wide[cols_to_sum].sum(axis=1, skipna=True)
            daily_total = daily_total.dropna()[lambda x: x != 0]

            if not daily_total.empty:
                all_positions_data.append(daily_total)
                logger.info(f"文件 {file_source_name} ('{maturity}'): 成功處理 {len(daily_total)} 筆數據。")

        except requests.exceptions.RequestException as e:
            logger.error(f"下載文件 {file_source_name} 失敗: {e}")
        except Exception as e:
            logger.error(f"處理文件 {file_source_name} 時發生未預期錯誤: {e}", exc_info=True)

    if not all_positions_data:
        logger.warning(f"未能從任何 NY Fed 文件中成功處理 '{series_name}' 數據。")
        return pd.Series(dtype='float64', name=series_name)

    full_series = pd.concat(all_positions_data).sort_index().groupby(level=0).last()

    save_series_to_db(full_series, db_ticker)

    filtered_series = full_series.loc[start_date:end_date].copy()
    filtered_series.name = series_name

    logger.info(f"成功合併所有 '{series_name}' 數據，篩選後得到 {len(filtered_series)} 筆有效數據。")
    return filtered_series

def fetch_nyfed_total_positions_data(start_date: str, end_date: str) -> pd.Series:
    return _fetch_and_process_files('total', start_date, end_date)

def fetch_nyfed_short_term_positions_data(start_date: str, end_date: str) -> pd.Series:
    return _fetch_and_process_files('short', start_date, end_date)

def fetch_nyfed_long_term_positions_data(start_date: str, end_date: str) -> pd.Series:
    return _fetch_and_process_files('long', start_date, end_date)