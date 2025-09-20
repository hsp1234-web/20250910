# -*- coding: utf-8 -*-
"""
壓力指數計算模組 (Stress Calculator)

功能：
- 基於合併後的數據，計算所有衍生指標。
- 計算各成分的滾動百分位排名。
- 根據設定的權重計算加權壓力指數。
- 對指數進行平滑處理。
- (可選) 計算 MACD 動能指標。
- 此模組的邏輯主要移植自 `一級交易pro.py` 的 Cell 8。
"""

import logging
import pandas as pd
import numpy as np

# 從設定檔導入專案設定
from services.bond_service.config import PROJECT_CONFIG

# 設定日誌
logger = logging.getLogger(__name__)

def calculate_stress_index(merged_df: pd.DataFrame, config: dict = PROJECT_CONFIG) -> pd.DataFrame:
    """
    計算所有衍生指標與最終的壓力指數。

    Args:
        merged_df (pd.DataFrame): 包含所有合併數據的 DataFrame。
        config (dict): 專案設定字典。

    Returns:
        pd.DataFrame: 包含所有計算結果的最終 DataFrame。
    """
    logger.info(f"開始計算壓力指數，輸入數據維度: {merged_df.shape}")
    if merged_df.empty:
        logger.warning("輸入的 merged_df 為空，無法進行計算。")
        return pd.DataFrame()

    final_df = merged_df.copy()

    # --- 1. 計算基本衍生指標 ---
    logger.info("步驟 1: 計算基本衍生指標...")

    # 計算利差 (10Y - 2Y)
    if 'DGS10' in final_df and 'DGS2' in final_df:
        final_df['Spread_10Y2Y'] = final_df['DGS10'] - final_df['DGS2']
        logger.debug("利差 (Spread_10Y2Y) 計算完成。")
    else:
        final_df['Spread_10Y2Y'] = np.nan
        logger.warning("缺少 DGS10 或 DGS2 數據，無法計算利差。")

    # 計算 SOFR 與 60 日移動平均的偏差
    if 'SOFR' in final_df and final_df['SOFR'].notna().any():
        min_periods_ma = 30
        if len(final_df['SOFR'].dropna()) >= min_periods_ma:
            final_df['SOFR_MA60'] = final_df['SOFR'].rolling(window=60, min_periods=min_periods_ma).mean()
            final_df['SOFR_Dev'] = final_df['SOFR'] - final_df['SOFR_MA60']
            logger.debug("SOFR 60日均線和偏差計算完成。")
        else:
            final_df['SOFR_MA60'], final_df['SOFR_Dev'] = np.nan, np.nan
            logger.warning(f"SOFR 數據點不足 {min_periods_ma}，無法計算60日均線。")
    else:
        final_df['SOFR_MA60'], final_df['SOFR_Dev'] = np.nan, np.nan
        logger.warning("缺少 SOFR 數據，無法計算均線和偏差。")

    # 計算持有量/準備金比率
    if 'Total_Gross_Positions_Millions' in final_df and 'Reserves' in final_df and \
       final_df['Total_Gross_Positions_Millions'].notna().any() and final_df['Reserves'].notna().any():
        reserves_safe = final_df['Reserves'].replace(0, np.nan)
        final_df['Pos_Res_Ratio'] = final_df['Total_Gross_Positions_Millions'] / reserves_safe
        final_df['Pos_Res_Ratio'].replace([np.inf, -np.inf], np.nan, inplace=True)
        logger.debug("持有量/準備金比率 (Pos_Res_Ratio) 計算完成。")
    else:
        final_df['Pos_Res_Ratio'] = np.nan
        logger.warning("缺少持有量或準備金數據，無法計算比率。")

    # --- 2. 計算壓力指數 ---
    logger.info("步驟 2: 計算壓力指數...")
    window = int(config.get('rolling_window_days', 252))
    min_periods_rank = int(window * 0.6)

    perc_ranks = pd.DataFrame(index=final_df.index)
    column_mapping = {
        'sofr_dev': 'SOFR_Dev', 'spread_inv': 'Spread_10Y2Y',
        'gross_pos': 'Total_Gross_Positions_Millions', 'move': 'Volatility_Index',
        'vix': 'VIX', 'pos_res_ratio': 'Pos_Res_Ratio'
    }

    for name, col in column_mapping.items():
        if col in final_df and final_df[col].notna().sum() >= min_periods_rank:
            rank_pct = final_df[col].rolling(window=window, min_periods=min_periods_rank).rank(pct=True)
            perc_ranks[name] = (1.0 - rank_pct) if name == 'spread_inv' else rank_pct
        else:
            perc_ranks[name] = np.nan
            logger.warning(f"成分 '{name}' ({col}) 數據不足，無法計算排名。")

    # 加權計算
    weights = config.get('weights', {})
    active_components = {k: v for k, v in weights.items() if k in perc_ranks.columns and perc_ranks[k].notna().any()}

    if not active_components:
        logger.error("無可用指標或權重，無法計算壓力指數。")
        final_df['Dealer_Stress_Index_Raw'] = np.nan
        final_df['Dealer_Stress_Index'] = np.nan
    else:
        total_weight = sum(active_components.values())
        weights_normalized = {k: v / total_weight for k, v in active_components.items()}

        combined_score = pd.Series(0.0, index=final_df.index)
        for name, weight in weights_normalized.items():
            rank_series = perc_ranks[name].fillna(0.5)
            if name == 'pos_res_ratio':
                threshold = config.get('threshold_ratio_color', 90)
                condition = (final_df['Pos_Res_Ratio'] >= threshold).astype(float).fillna(0.0)
                combined_score += rank_series * condition * weight
            else:
                combined_score += rank_series * weight

        final_df['Dealer_Stress_Index_Raw'] = (combined_score * 100).clip(0, 100)

        # 指數平滑
        smoothing_window = int(config.get('smoothing_window_stress_index', 5))
        if smoothing_window > 1:
            final_df['Dealer_Stress_Index'] = final_df['Dealer_Stress_Index_Raw'].rolling(
                window=smoothing_window, min_periods=1, center=True
            ).mean().clip(0, 100)
        else:
            final_df['Dealer_Stress_Index'] = final_df['Dealer_Stress_Index_Raw']
        logger.info("壓力指數計算與平滑完成。")

    # --- 3. 計算 MACD 動能 (可選) ---
    if config.get('enable_macd_momentum_plot', False) and 'Dealer_Stress_Index' in final_df and final_df['Dealer_Stress_Index'].notna().any():
        logger.info("步驟 3: 計算 MACD 動能指標...")
        params = config.get('macd_params', {})
        colors = config.get('macd_colors', {})
        fast, slow, signal = params.get('fast', 12), params.get('slow', 26), params.get('signal', 9)

        base_series = final_df['Dealer_Stress_Index'].dropna()
        if len(base_series) > slow:
            ema_fast = base_series.ewm(span=fast, adjust=False).mean()
            ema_slow = base_series.ewm(span=slow, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=signal, adjust=False).mean()
            histogram = macd_line - signal_line
            final_df['Stress_Index_MACD_Hist'] = histogram.reindex(final_df.index)

            # 計算顏色
            hist_diff = final_df['Stress_Index_MACD_Hist'].diff()
            conditions = [
                (hist_diff > 0) & (final_df['Stress_Index_MACD_Hist'] >= 0),
                (hist_diff > 0) & (final_df['Stress_Index_MACD_Hist'] < 0),
                (hist_diff <= 0)
            ]
            color_values = [colors.get('blue'), colors.get('green'), colors.get('red')]
            final_df['Stress_Index_MACD_Color'] = np.select(conditions, color_values, default='grey')
            logger.debug("MACD 指標與顏色計算完成。")
        else:
            logger.warning(f"壓力指數數據點不足 {slow}，無法計算 MACD。")
            final_df['Stress_Index_MACD_Hist'] = np.nan
            final_df['Stress_Index_MACD_Color'] = 'grey'
    else:
        final_df['Stress_Index_MACD_Hist'] = np.nan
        final_df['Stress_Index_MACD_Color'] = 'grey'

    logger.info("所有指標計算完成。")
    return final_df
