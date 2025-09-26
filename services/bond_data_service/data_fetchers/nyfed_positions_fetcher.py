# services/bond_data_service/data_fetchers/nyfed_positions_fetcher.py
import pandas as pd
import requests
import io
import logging
from typing import List, Literal

# --- 常數 ---
NY_FED_URLS = [
    "https://markets.newyorkfed.org/api/pd/get/SBN2024/timeseries/"
    "PDPOSGSC-L2_PDPOSGSC-G2L3_PDPOSGSC-G3L6_PDPOSGSC-G6L7_"
    "PDPOSGSC-G7L11_PDPOSGSC-G11L21_PDPOSGSC-G21.xlsx",
    "https://markets.newyorkfed.org/api/pd/get/SBN2022/timeseries/"
    "PDPOSGSC-L2_PDPOSGSC-G2L3_PDPOSGSC-G3L6_PDPOSGSC-G6L7_"
    "PDPOSGSC-G7L11_PDPOSGSC-G11L21_PDPOSGSC-G21.xlsx",
    "https://markets.newyorkfed.org/api/pd/get/SBN2015/timeseries/"
    "PDPOSGSC-L2_PDPOSGSC-G2L3_PDPOSGSC-G3L6_PDPOSGSC-G6L7_"
    "PDPOSGSC-G7L11_PDPOSGSC-G11.xlsx",
    "https://markets.newyorkfed.org/api/pd/get/SBN2013/timeseries/"
    "PDPOSGSC-L2_PDPOSGSC-G2L3_PDPOSGSC-G3L6_PDPOSGSC-G6L7_"
    "PDPOSGSC-G7L11_PDPOSGSC-G11.xlsx",
    "https://markets.newyorkfed.org/api/pd/get/SBP2013/timeseries/"
    "PDPUSGCS3LNOP_PDPUSGCS36NOP_PDPUSGCS611NOP_PDPUSGCSM11NOP.xlsx",
    "https://markets.newyorkfed.org/api/pd/get/SBP2001/timeseries/"
    "PDPUSGCS5LNOP_PDPUSGCS5MNOP.xlsx"
]

# 定義不同期限的欄位
# 短期: <= 3年
SBN_SHORT_TERM_COLS = ['PDPOSGSC-L2', 'PDPOSGSC-G2L3']
SBP2013_SHORT_TERM_COLS = ['PDPUSGCS3LNOP']
SBP2001_SHORT_TERM_COLS = ['PDPUSGCS5LNOP']

# 長期: > 7年
SBN_LONG_TERM_COLS = ['PDPOSGSC-G7L11', 'PDPOSGSC-G11L21', 'PDPOSGSC-G21', 'PDPOSGSC-G11']
SBP2013_LONG_TERM_COLS = ['PDPUSGCS611NOP', 'PDPUSGCSM11NOP']
SBP2001_LONG_TERM_COLS = ['PDPUSGCS5MNOP']

# 設置日誌
logger = logging.getLogger(__name__)

def _fetch_and_process_files(maturity: Literal['total', 'short', 'long']) -> pd.Series:
    """
    從 NY Fed 網站抓取、解析並合併多個 Excel 檔案的內部核心函式。

    Args:
        maturity (str): 要計算的期限類型 ('total', 'short', 'long')。

    Returns:
        pd.Series: 一個時間序列，索引為日期，值為對應期限的持有量 (百萬美元)。
    """
    logger.info(f"開始為 '{maturity}' 部位從 NY Fed 抓取數據...")
    print(f"開始為 '{maturity}' 部位從 NY Fed 抓取數據...")
    all_positions_data = []

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })

    for url in NY_FED_URLS:
        file_source_name = url.split('/')[-3] if len(url.split('/')) > 2 else url.split('/')[-1]
        logger.info(f"正在為 '{maturity}' 部位處理文件: {file_source_name}")
        print(f"正在為 '{maturity}' 部位處理文件: {file_source_name}")

        try:
            response = session.get(url, timeout=120)
            response.raise_for_status()
            excel_content = io.BytesIO(response.content)

            header_row = None
            data_positions_long = None
            possible_headers = [3, 4, 0]

            for h in possible_headers:
                try:
                    df_peek = pd.read_excel(excel_content, header=h, nrows=5, engine='openpyxl')
                    excel_content.seek(0)
                    cols_lower = [str(c).lower() for c in df_peek.columns]
                    if 'time series' in cols_lower and ('value' in cols_lower or 'value (millions)' in cols_lower):
                        header_row = h
                        date_col_name = df_peek.columns[0]
                        data_positions_long = pd.read_excel(excel_content, header=header_row, index_col=date_col_name, parse_dates=True, engine='openpyxl')
                        break
                except Exception:
                    excel_content.seek(0)
                    continue

            if data_positions_long is None:
                logger.warning(f"文件 {file_source_name}: 無法自動檢測有效表頭，跳過。")
                continue

            data_positions_long = data_positions_long[pd.to_datetime(data_positions_long.index, errors='coerce').notna()]
            data_positions_long.index = data_positions_long.index.normalize()

            actual_ts_col = next((c for c in data_positions_long.columns if str(c).lower() == 'time series'), None)
            actual_val_col = next((c for c in data_positions_long.columns if str(c).lower().startswith('value')), None)

            if not actual_ts_col or not actual_val_col:
                logger.warning(f"文件 {file_source_name}: 缺少 'Time Series' 或 'Value' 欄位，跳過。")
                continue

            data_positions_long[actual_val_col] = pd.to_numeric(data_positions_long[actual_val_col], errors='coerce')
            data_positions_long.dropna(subset=[actual_val_col, actual_ts_col], inplace=True)

            if data_positions_long.empty:
                continue

            data_positions_long.reset_index(inplace=True)
            date_col_actual = data_positions_long.columns[0]
            data_positions_long = data_positions_long.groupby([date_col_actual, actual_ts_col])[actual_val_col].mean().reset_index()
            data_positions_wide = pd.pivot_table(data_positions_long, index=date_col_actual, columns=actual_ts_col, values=actual_val_col)

            target_cols: List[str] = []
            if 'SBN' in url:
                if maturity == 'total': target_cols = [c for c in data_positions_wide.columns if isinstance(c, str) and c.startswith('PDPOSGSC-')]
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

            cols_to_sum_actual = [c for c in target_cols if c in data_positions_wide.columns]
            if not cols_to_sum_actual:
                continue

            daily_total_millions = data_positions_wide[cols_to_sum_actual].sum(axis=1, skipna=True)
            daily_total_millions = daily_total_millions.dropna()[lambda x: x != 0]

            if not daily_total_millions.empty:
                all_positions_data.append(daily_total_millions)
                logger.info(f"文件 {file_source_name} ('{maturity}'): 成功處理 {len(daily_total_millions)} 筆數據。")
                print(f"文件 {file_source_name} ('{maturity}'): 成功處理 {len(daily_total_millions)} 筆數據。")

        except requests.exceptions.RequestException as e:
            logger.error(f"下載文件 {file_source_name} 失敗: {e}")
        except Exception as e:
            logger.error(f"處理文件 {file_source_name} 時發生未預期錯誤: {e}", exc_info=True)

    if not all_positions_data:
        logger.warning(f"未能從任何 NY Fed 文件中成功處理 '{maturity}' 部位數據。")
        return pd.Series(dtype='float64')

    combined_positions = pd.concat(all_positions_data).sort_index()
    final_series = combined_positions.groupby(level=0).last()
    final_series.name = f'dealer_positions_{maturity}'

    logger.info(f"成功合併所有 '{maturity}' 部位數據，最終得到 {len(final_series)} 筆有效數據。")
    print(f"成功合併所有 '{maturity}' 部位數據，最終得到 {len(final_series)} 筆有效數據。")
    return final_series

def fetch_nyfed_total_positions_data(api_key: str = None) -> pd.Series:
    """抓取一級交易商的公債總持有量。"""
    return _fetch_and_process_files('total')

def fetch_nyfed_short_term_positions_data(api_key: str = None) -> pd.Series:
    """抓取一級交易商的短期公債持有量。"""
    return _fetch_and_process_files('short')

def fetch_nyfed_long_term_positions_data(api_key: str = None) -> pd.Series:
    """抓取一級交易商的長期公債持有量。"""
    return _fetch_and_process_files('long')