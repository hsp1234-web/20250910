# services/bond_data_service/stress_index_calculator.py

import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional
from cachetools import cached, TTLCache
from data_manager import DataManager

logger = logging.getLogger(__name__)

# --- 快取設定 ---
# 建立一個 TTL (Time-To-Live) 快取
# maxsize: 快取中最多可以儲存 10 組不同的計算結果
# ttl: 每筆快取結果的存活時間為 300 秒 (5 分鐘)
metrics_cache = TTLCache(maxsize=10, ttl=300)

# 自訂快取鍵產生函式
# 我們只根據 start_date 和 end_date 來決定是否命中快取，
# 忽略 data_manager 實例，因為它在應用程式生命週期中是同一個物件，但不可雜湊。
def cache_key(data_manager, start_date, end_date):
    return (start_date, end_date)

# --- 指標計算設定 ---

# 更新後的權重，加入了高收益債利差(HYG價格的反轉指標)，並調整了其他權重以維持總和為1.0
STRESS_INDEX_WEIGHTS = {
    'sofr_dev': 0.25,      # SOFR 偏離
    'spread_inv': 0.10,    # 10Y-2Y 利差反轉
    'hys_inv': 0.10,       # 高收益債利差反轉 (HYG 價格反轉)
    'gross_pos': 0.05,     # 總部位
    'move': 0.25,          # MOVE 指數
    'vix': 0.15,           # VIX 指數
    'pos_res_ratio': 0.10  # 部位/準備金比率
}
ROLLING_WINDOW_DAYS = 252
SMOOTHING_WINDOW = 5
POS_RES_RATIO_THRESHOLD = 90

@cached(cache=metrics_cache, key=cache_key)
def calculate_full_metrics(data_manager: DataManager, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    計算所有指標，包括基礎數據、衍生指標和最終的壓力指數。
    此函式的計算結果會被快取，以提升重複請求的效能。

    Args:
        data_manager (DataManager): 用於獲取基礎數據的 DataManager 實例。
        start_date (str): 數據開始日期 (YYYY-MM-DD)。
        end_date (str): 數據結束日期 (YYYY-MM-DD)。

    Returns:
        Optional[pd.DataFrame]: 一個包含所有計算結果的完整 DataFrame，如果失敗則返回 None。
    """
    # 1. 獲取所有需要的基礎數據
    logger.info("開始獲取所有基礎數據...")
    indicator_list = [
        "sofr", "dgs10", "dgs2", "vix", "us_high_yield_spread",
        "dealer_net_positions", "wresbal", "rrp",
        "dealer_long_term_positions", "dealer_short_term_positions"
    ]
    # 注意：'move_index' 在目前的 fetcher 中不存在，暫時從列表中移除。
    # 如果需要，可以添加一個 yahoo_finance_fetcher 來獲取它。

    all_series: Dict[str, pd.Series] = {}
    for indicator in indicator_list:
        series = data_manager.get_series(indicator, start_date, end_date)
        if series is not None:
            all_series[indicator] = series
        else:
            logger.warning(f"獲取 '{indicator}' 數據失敗，將影響後續計算。")
            # 創建一個空的 Series 以避免錯誤
            all_series[indicator] = pd.Series(dtype='float64', name=indicator)

    # 合併所有 Series 成一個 DataFrame
    df = pd.concat(all_series.values(), axis=1, join='outer')
    # 向前填充以處理不同頻率（特別是週頻的 wresbal 和 nyfed_positions）
    df = df.ffill()

    if df.empty:
        logger.error("無法獲取任何基礎數據，計算終止。")
        return None

    # 2. 計算衍生指標
    logger.info("正在計算衍生指標...")
    df['spread_10y2y'] = df['dgs10'] - df['dgs2']
    df['sofr_ma60'] = df['sofr'].rolling(window=60, min_periods=30).mean()
    df['sofr_dev'] = df['sofr'] - df['sofr_ma60']
    reserves_safe = df['wresbal'].replace(0, np.nan)
    df['pos_res_ratio'] = df['dealer_net_positions'] / reserves_safe

    # 3. 計算各成分的滾動百分位排名
    logger.info("正在計算各成分的滾動百分位排名...")
    perc_ranks = pd.DataFrame(index=df.index)
    min_periods_rank = int(ROLLING_WINDOW_DAYS * 0.6)

    component_map = {
        'sofr_dev': 'sofr_dev',
        'spread_inv': 'spread_10y2y',
        'hys_inv': 'us_high_yield_spread',
        'gross_pos': 'dealer_net_positions',
        'vix': 'vix',
        'pos_res_ratio': 'pos_res_ratio'
    }
    # 'move' 指標暫時未包含

    for name, col in component_map.items():
        if col in df and df[col].notna().sum() >= min_periods_rank:
            series_to_rank = df[col]
            rank_pct = series_to_rank.rolling(window=ROLLING_WINDOW_DAYS, min_periods=min_periods_rank).rank(pct=True)
            # 對於反轉指標，排名越高代表壓力越小，所以用 1 減去它
            if name in ['spread_inv', 'hys_inv']:
                perc_ranks[name] = 1.0 - rank_pct
            else:
                perc_ranks[name] = rank_pct
        else:
            logger.warning(f"成分 '{name}' (來自欄位 '{col}') 數據不足，無法計算其排名。")
            perc_ranks[name] = np.nan

    # 4. 加權計算壓力指數
    logger.info("正在加權計算壓力指數...")
    active_weights = {k: v for k, v in STRESS_INDEX_WEIGHTS.items() if k in perc_ranks.columns and perc_ranks[k].notna().any()}

    if not active_weights:
        logger.error("無可用指標的排名數據，無法計算壓力指數。")
        df['dealer_stress_index'] = np.nan
        return df

    total_weight = sum(active_weights.values())
    weights_normalized = {k: v / total_weight for k, v in active_weights.items()}
    logger.info(f"使用的指標及其正規化權重: {weights_normalized}")

    ratio_high_condition = (df['pos_res_ratio'] >= POS_RES_RATIO_THRESHOLD).astype(float).fillna(0.0)
    combined_score = pd.Series(0.0, index=df.index)
    for name, weight in weights_normalized.items():
        rank_series = perc_ranks[name].fillna(0.5)
        if name == 'pos_res_ratio':
            combined_score += rank_series * ratio_high_condition * weight
        else:
            combined_score += rank_series * weight

    df['dealer_stress_index_raw'] = (combined_score * 100).clip(0, 100)

    # 5. 指數平滑
    if SMOOTHING_WINDOW > 1:
        min_periods_smooth = max(1, int(SMOOTHING_WINDOW * 0.5))
        df['dealer_stress_index'] = df['dealer_stress_index_raw'].rolling(
            window=SMOOTHING_WINDOW, min_periods=min_periods_smooth, center=True
        ).mean().clip(0, 100)
    else:
        df['dealer_stress_index'] = df['dealer_stress_index_raw']

    # 6. 計算 MACD
    logger.info("正在計算 MACD 指標...")
    macd_fast, macd_slow, macd_signal = 12, 26, 9
    base_series = df['dealer_stress_index'].dropna()
    if len(base_series) > macd_slow:
        ema_fast = base_series.ewm(span=macd_fast, adjust=False).mean()
        ema_slow = base_series.ewm(span=macd_slow, adjust=False).mean()
        df['macd_line'] = (ema_fast - ema_slow).reindex(df.index)
        df['macd_signal_line'] = df['macd_line'].ewm(span=macd_signal, adjust=False).mean()
        df['macd_hist'] = df['macd_line'] - df['macd_signal_line']
    else:
        df[['macd_line', 'macd_signal_line', 'macd_hist']] = np.nan

    logger.info(f"完整指標計算完成，DataFrame 維度: {df.shape}")
    return df