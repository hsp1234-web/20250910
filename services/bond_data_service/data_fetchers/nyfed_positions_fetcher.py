# services/bond_data_service/data_fetchers/nyfed_positions_fetcher.py
import pandas as pd
import requests
import io
import logging

# --- 常數 ---
# 從 '一級交易pro.py' 的 PROJECT_CONFIG 中提取的設定
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

SBP2013_COLS = ['PDPUSGCS3LNOP', 'PDPUSGCS36NOP', 'PDPUSGCS611NOP', 'PDPUSGCSM11NOP']
SBP2001_COLS = ['PDPUSGCS5LNOP', 'PDPUSGCS5MNOP']

# 設置日誌
logger = logging.getLogger(__name__)

def fetch_nyfed_positions_data(api_key: str = None):
    """
    從 NY Fed 網站抓取、解析並合併多個 Excel 檔案，以獲取一級交易商的公債持有量。
    此函式不使用 api_key，保留參數是為了與其他 fetcher 保持一致。

    Returns:
        pd.Series: 一個時間序列，索引為日期，值為總持有量 (百萬美元)。
                   如果失敗則回傳一個空的 Series。
    """
    logger.info("開始從 NY Fed 抓取一級交易商持有量數據...")
    print("開始從 NY Fed 抓取一級交易商持有量數據...")
    all_positions_data = []

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })

    for url in NY_FED_URLS:
        file_source_name = url.split('/')[-3] if len(url.split('/')) > 2 else url.split('/')[-1]
        logger.info(f"正在處理文件: {file_source_name}")
        print(f"正在處理文件: {file_source_name}")

        try:
            # 1. 下載 Excel 文件
            response = session.get(url, timeout=120)
            response.raise_for_status()
            excel_content = io.BytesIO(response.content)

            # 2. 解析 Excel (自動檢測表頭)
            header_row = None
            data_positions_long = None
            possible_headers = [3, 4, 0] # 根據觀察，這些是可能的表頭行

            for h in possible_headers:
                try:
                    df_peek = pd.read_excel(excel_content, header=h, nrows=5, engine='openpyxl')
                    excel_content.seek(0)
                    cols_lower = [str(c).lower() for c in df_peek.columns]
                    if 'time series' in cols_lower and ('value' in cols_lower or 'value (millions)' in cols_lower):
                        header_row = h
                        date_col_name = df_peek.columns[0] # 假設日期總在第一列
                        data_positions_long = pd.read_excel(excel_content, header=header_row, index_col=date_col_name, parse_dates=True, engine='openpyxl')
                        logger.info(f"在第 {h+1} 行找到有效表頭。")
                        break
                except Exception:
                    excel_content.seek(0)
                    continue

            if data_positions_long is None:
                logger.warning(f"文件 {file_source_name}: 無法自動檢測有效的表頭。跳過此文件。")
                continue

            # 3. 清理長格式數據並轉換為寬格式
            # 將索引轉換為 datetime 物件，並移除轉換失敗的 NaT (Not a Time) 行
            data_positions_long = data_positions_long[pd.to_datetime(data_positions_long.index, errors='coerce').notna()]
            data_positions_long.index = data_positions_long.index.normalize()

            actual_ts_col = next((c for c in data_positions_long.columns if str(c).lower() == 'time series'), None)
            actual_val_col = next((c for c in data_positions_long.columns if str(c).lower().startswith('value')), None)

            if not actual_ts_col or not actual_val_col:
                logger.warning(f"文件 {file_source_name}: 清理後缺少 'Time Series' 或 'Value' 欄位。跳過。")
                continue

            data_positions_long[actual_val_col] = pd.to_numeric(data_positions_long[actual_val_col], errors='coerce')
            data_positions_long.dropna(subset=[actual_val_col, actual_ts_col], inplace=True)

            if data_positions_long.empty:
                logger.warning(f"文件 {file_source_name}: 清理後無有效數據。跳過。")
                continue

            data_positions_long.reset_index(inplace=True)
            date_col_actual = data_positions_long.columns[0]

            data_positions_long = data_positions_long.groupby(
                [date_col_actual, actual_ts_col]
            )[actual_val_col].mean().reset_index()

            data_positions_wide = pd.pivot_table(data_positions_long, index=date_col_actual, columns=actual_ts_col, values=actual_val_col, aggfunc='mean')

            # 4. 加總持有量
            target_cols = []
            if 'SBN' in url:
                target_cols = [c for c in data_positions_wide.columns if isinstance(c, str) and c.startswith('PDPOSGSC-')]
            elif 'SBP2013' in url:
                target_cols = SBP2013_COLS
            elif 'SBP2001' in url:
                target_cols = SBP2001_COLS

            cols_to_sum_actual = [c for c in target_cols if c in data_positions_wide.columns]
            if not cols_to_sum_actual:
                logger.warning(f"文件 {file_source_name}: 未找到任何預期的目標欄位。跳過加總。")
                continue

            daily_total_millions = data_positions_wide[cols_to_sum_actual].sum(axis=1, skipna=True)
            daily_total_millions = daily_total_millions.dropna()
            daily_total_millions = daily_total_millions[daily_total_millions != 0]

            if not daily_total_millions.empty:
                all_positions_data.append(daily_total_millions)
                logger.info(f"文件 {file_source_name}: 成功處理並獲得 {len(daily_total_millions)} 筆數據。")
                print(f"文件 {file_source_name}: 成功處理並獲得 {len(daily_total_millions)} 筆數據。")

        except requests.exceptions.RequestException as e:
            logger.error(f"下載文件 {file_source_name} 失敗: {e}")
        except Exception as e:
            logger.error(f"處理文件 {file_source_name} 時發生未預期錯誤: {e}", exc_info=True)

    # 5. 合併所有數據
    if not all_positions_data:
        logger.warning("未能從任何 NY Fed 文件中成功處理數據。")
        return pd.Series(dtype='float64')

    combined_positions = pd.concat(all_positions_data)
    combined_positions = combined_positions.sort_index()
    # 處理重疊日期，保留最後（通常是最新）的值
    final_series = combined_positions.groupby(level=0).last()
    final_series.name = 'dealer_positions'

    logger.info(f"成功合併所有 NY Fed 數據，最終得到 {len(final_series)} 筆有效數據。")
    print(f"成功合併所有 NY Fed 數據，最終得到 {len(final_series)} 筆有效數據。")
    return final_series