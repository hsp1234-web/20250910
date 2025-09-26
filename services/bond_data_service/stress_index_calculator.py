# services/bond_data_service/stress_index_calculator.py

import pandas as pd
import numpy as np
import logging
from .data_manager import DataManager

logger = logging.getLogger(__name__)

# 從 '一級交易pro.py' 的 PROJECT_CONFIG 中提取的計算參數
# 這些參數未來可以移到更正式的設定檔中
STRESS_INDEX_WEIGHTS = {
    'sofr_dev': 0.35,
    'spread_inv': 0.10,
    'gross_pos': 0.05,
    'move': 0.25,
    'vix': 0.15,
    'pos_res_ratio': 0.10
}
ROLLING_WINDOW_DAYS = 252
SMOOTHING_WINDOW = 5
POS_RES_RATIO_THRESHOLD = 90

def get_required_data(data_manager: DataManager) -> pd.DataFrame:
    """
    使用 DataManager 獲取計算壓力指數所需的所有基礎數據，並整合成一個 DataFrame。
    """
    indicator_list = [
        'sofr', 'dgs10', 'dgs2', 'move_index', 'vix',
        'dealer_positions', 'wresbal' # WRESBAL is 'Reserves'
    ]

    all_series = {}
    logger.info("開始獲取計算壓力指數所需的基礎數據...")
    print("開始獲取計算壓力指數所需的基礎數據...")

    for indicator in indicator_list:
        try:
            # 嘗試從資料庫獲取數據
            data = data_manager.get_data(indicator)
            if not data:
                # 如果沒有數據，觸發抓取
                logger.info(f"資料庫中無 '{indicator}' 數據，觸發自動抓取...")
                print(f"資料庫中無 '{indicator}' 數據，觸發自動抓取...")
                data_manager.fetch_and_store_data(indicator)
                data = data_manager.get_data(indicator)

            if data:
                # 將 list of dicts 轉換為 pandas Series
                df = pd.DataFrame(data)
                df['date'] = pd.to_datetime(df['date'])
                series = df.set_index('date')['value']
                series.name = indicator
                all_series[indicator] = series
                logger.info(f"成功獲取 '{indicator}' 數據 ({len(series)} 筆)。")
                print(f"成功獲取 '{indicator}' 數據 ({len(series)} 筆)。")
            else:
                logger.warning(f"獲取 '{indicator}' 數據失敗，將使用空值處理。")
                print(f"警告：獲取 '{indicator}' 數據失敗。")
                all_series[indicator] = pd.Series(dtype='float64', name=indicator)

        except Exception as e:
            logger.error(f"獲取基礎數據 '{indicator}' 時發生嚴重錯誤: {e}", exc_info=True)
            all_series[indicator] = pd.Series(dtype='float64', name=indicator)

    # 合併所有 Series 成一個 DataFrame
    # 使用 outer join 保留所有日期，並向前填充以處理不同頻率的數據
    combined_df = pd.concat(all_series.values(), axis=1, join='outer').ffill()
    return combined_df


def calculate_stress_index(data_manager: DataManager) -> pd.Series:
    """
    計算一級交易商壓力指數。

    Args:
        data_manager (DataManager): 用於獲取基礎數據的 DataManager 實例。

    Returns:
        pd.Series: 包含最終壓力指數的 pandas Series。
    """
    # 1. 獲取並整合所有需要的數據
    df = get_required_data(data_manager)

    if df.empty:
        logger.error("無法獲取任何基礎數據，無法計算壓力指數。")
        return pd.Series(dtype='float64', name='dealer_stress_index')

    # 2. 計算衍生指標
    logger.info("正在計算衍生指標...")
    print("正在計算衍生指標...")
    df['spread_10y2y'] = df['dgs10'] - df['dgs2']
    df['sofr_ma60'] = df['sofr'].rolling(window=60, min_periods=30).mean()
    df['sofr_dev'] = df['sofr'] - df['sofr_ma60']

    # 處理準備金為 0 的情況
    reserves_safe = df['wresbal'].replace(0, np.nan)
    df['pos_res_ratio'] = df['dealer_positions'] / reserves_safe

    # 3. 計算各成分的滾動百分位排名
    logger.info("正在計算各成分的滾動百分位排名...")
    print("正在計算各成分的滾動百分位排名...")
    perc_ranks = pd.DataFrame(index=df.index)
    min_periods_rank = int(ROLLING_WINDOW_DAYS * 0.6)

    # 指標與其在 DataFrame 中的欄位名稱映射
    component_map = {
        'sofr_dev': 'sofr_dev',
        'spread_inv': 'spread_10y2y',
        'gross_pos': 'dealer_positions',
        'move': 'move_index',
        'vix': 'vix',
        'pos_res_ratio': 'pos_res_ratio'
    }

    for name, col in component_map.items():
        if col in df and df[col].notna().sum() >= min_periods_rank:
            series_to_rank = df[col]
            rank_pct = series_to_rank.rolling(window=ROLLING_WINDOW_DAYS, min_periods=min_periods_rank).rank(pct=True)
            perc_ranks[name] = 1.0 - rank_pct if name == 'spread_inv' else rank_pct
        else:
            logger.warning(f"成分 '{name}' 數據不足，無法計算其排名。")
            perc_ranks[name] = np.nan

    # 4. 加權計算壓力指數
    logger.info("正在加權計算壓力指數...")
    print("正在加權計算壓力指數...")

    active_weights = {k: v for k, v in STRESS_INDEX_WEIGHTS.items() if k in perc_ranks.columns and perc_ranks[k].notna().any()}
    total_weight = sum(active_weights.values())

    if total_weight <= 0:
        logger.error("無可用指標或權重為零，無法計算壓力指數。")
        return pd.Series(dtype='float64', name='dealer_stress_index')

    weights_normalized = {k: v / total_weight for k, v in active_weights.items()}

    # 特殊處理 Pos/Res Ratio 的條件權重
    ratio_high_condition = (df['pos_res_ratio'] >= POS_RES_RATIO_THRESHOLD).astype(float).fillna(0.0)

    combined_score = pd.Series(0.0, index=df.index)
    for name, weight in weights_normalized.items():
        rank_series = perc_ranks[name].fillna(0.5) # 用中間值填充排名中的 NaN
        if name == 'pos_res_ratio':
            combined_score += rank_series * ratio_high_condition * weight
        else:
            combined_score += rank_series * weight

    # 映射到 0-100 範圍
    raw_stress_index = (combined_score * 100).clip(0, 100)

    # 5. 指數平滑
    logger.info("正在平滑壓力指數...")
    print("正在平滑壓力指數...")
    if SMOOTHING_WINDOW > 1:
        min_periods_smooth = max(1, int(SMOOTHING_WINDOW * 0.5))
        final_stress_index = raw_stress_index.rolling(
            window=SMOOTHING_WINDOW, min_periods=min_periods_smooth, center=True
        ).mean().clip(0, 100)
    else:
        final_stress_index = raw_stress_index

    final_stress_index.name = 'dealer_stress_index'

    # 移除頭尾的 NaN 值
    final_stress_index = final_stress_index.dropna()

    logger.info(f"壓力指數計算完成，共產生 {len(final_stress_index)} 筆有效數據。")
    print(f"壓力指數計算完成，共產生 {len(final_stress_index)} 筆有效數據。")
    return final_stress_index