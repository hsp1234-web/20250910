# poc/bond_data_service_v2/service.py
# 繁體中文註解：業務邏輯服務層

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd
from cachetools import TTLCache, cached

from .repository import DataRepository

logger = logging.getLogger(__name__)

# --- 指標計算設定 (常數) ---
STRESS_INDEX_WEIGHTS = {
    'sofr_dev': 0.25,
    'spread_inv': 0.10,
    'hys_inv': 0.10,
    'gross_pos': 0.05,
    'move': 0.25,
    'vix': 0.15,
    'pos_res_ratio': 0.10
}
ROLLING_WINDOW_DAYS = 252
SMOOTHING_WINDOW = 5
POS_RES_RATIO_THRESHOLD = 90

# --- 業務服務類別 ---

class StressIndexService:
    """
    封裝所有與壓力指標計算相關的業務邏輯。
    這個服務是無狀態的，它依賴於倉儲層來獲取數據。
    """
    def __init__(self, repository: DataRepository):
        self.repository = repository
        # 為每個服務實例建立一個獨立的快取
        self.metrics_cache = TTLCache(maxsize=10, ttl=300)

    # 新策略：直接在裝飾器中使用 lambda 產生快取鍵，
    # 徹底繞開任何與實例方法 `_cache_key` 相關的潛在問題。
    # 舊的 _cache_key 方法將被移除。
    @cached(
        cache=lambda self: self.metrics_cache,
        key=lambda self, start_date, end_date: (start_date, end_date)
    )
    def calculate_full_metrics(self, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        計算所有指標，包括基礎數據、衍生指標和最終的壓力指數。
        此方法的計算結果會被快取。
        """
        # 1. 獲取所有需要的基礎數據 (透過倉儲層)
        logger.info("服務層：開始從倉儲層獲取所有基礎數據...")
        indicator_list = [
            "sofr", "dgs10", "dgs2", "vix", "us_high_yield_spread",
            "dealer_net_positions", "wresbal", "rrp",
            "dealer_long_term_positions", "dealer_short_term_positions"
        ]
        all_series: Dict[str, pd.Series] = {}
        for indicator in indicator_list:
            series = self.repository.get_series(indicator, start_date, end_date)
            if series is not None and not series.empty:
                all_series[indicator] = series
            else:
                logger.warning(f"倉儲層未能提供 '{indicator}' 的數據，將在計算中忽略。")

        if not all_series:
            logger.error("所有基礎指標均未能獲取，計算終止。")
            return None

        df = pd.concat(all_series.values(), axis=1, join='outer').ffill()
        if df.empty:
            logger.error("無法合併任何基礎數據，計算終止。")
            return None

        # 2. 計算衍生指標 (加入保護性檢查)
        logger.info("服務層：正在計算衍生指標...")
        if 'dgs10' in df.columns and 'dgs2' in df.columns:
            df['spread_10y2y'] = df['dgs10'] - df['dgs2']
        else:
            df['spread_10y2y'] = np.nan
            logger.warning("服務層：缺少 'dgs10' 或 'dgs2'，無法計算利差。")

        if 'sofr' in df.columns:
            df['sofr_ma60'] = df['sofr'].rolling(window=60, min_periods=30).mean()
            df['sofr_dev'] = df['sofr'] - df['sofr_ma60']
        else:
            df['sofr_ma60'] = np.nan
            df['sofr_dev'] = np.nan
            logger.warning("服務層：缺少 'sofr'，無法計算其偏離。")

        if 'dealer_net_positions' in df.columns and 'wresbal' in df.columns:
            reserves_safe = df['wresbal'].replace(0, np.nan)
            df['pos_res_ratio'] = df['dealer_net_positions'] / reserves_safe
        else:
            df['pos_res_ratio'] = np.nan
            logger.warning("服務層：缺少部位或準備金數據，無法計算其比率。")

        # 3. 計算滾動百分位排名
        logger.info("服務層：正在計算滾動百分位排名...")
        perc_ranks = pd.DataFrame(index=df.index)
        min_periods_rank = int(ROLLING_WINDOW_DAYS * 0.6)
        component_map = {
            'sofr_dev': 'sofr_dev', 'spread_inv': 'spread_10y2y',
            'hys_inv': 'us_high_yield_spread', 'gross_pos': 'dealer_net_positions',
            'vix': 'vix', 'pos_res_ratio': 'pos_res_ratio'
        }
        for name, col in component_map.items():
            if col in df and df[col].notna().sum() >= min_periods_rank:
                series_to_rank = df[col]
                rank_pct = series_to_rank.rolling(window=ROLLING_WINDOW_DAYS, min_periods=min_periods_rank).rank(pct=True)
                perc_ranks[name] = 1.0 - rank_pct if name in ['spread_inv', 'hys_inv'] else rank_pct
            else:
                perc_ranks[name] = np.nan

        # 4. 加權計算壓力指數
        logger.info("服務層：正在加權計算壓力指數...")
        active_weights = {k: v for k, v in STRESS_INDEX_WEIGHTS.items() if k in perc_ranks.columns and perc_ranks[k].notna().any()}
        if not active_weights:
            df['dealer_stress_index'] = np.nan
            return df
        total_weight = sum(active_weights.values())
        weights_normalized = {k: v / total_weight for k, v in active_weights.items()}

        ratio_high_condition = (df['pos_res_ratio'] >= POS_RES_RATIO_THRESHOLD).astype(float).fillna(0.0)
        combined_score = pd.Series(0.0, index=df.index)
        for name, weight in weights_normalized.items():
            rank_series = perc_ranks[name].fillna(0.5)
            combined_score += rank_series * ratio_high_condition * weight if name == 'pos_res_ratio' else rank_series * weight

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
        logger.info("服務層：正在計算 MACD 指標...")
        macd_fast, macd_slow, macd_signal = 12, 26, 9
        base_series = df['dealer_stress_index'].dropna()
        if len(base_series) > macd_slow:
            ema_fast = base_series.ewm(span=macd_fast, adjust=False).mean()
            ema_slow = base_series.ewm(span=macd_slow, adjust=False).mean()
            df['macd_line'] = ema_fast - ema_slow
            df['macd_signal_line'] = df['macd_line'].ewm(span=macd_signal, adjust=False).mean()
            df['macd_hist'] = df['macd_line'] - df['macd_signal_line']
        else:
            df[['macd_line', 'macd_signal_line', 'macd_hist']] = np.nan

        logger.info(f"服務層：完整指標計算完成，DataFrame 維度: {df.shape}")
        return df