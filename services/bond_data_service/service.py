# services/bond_data_service/service.py
import logging
from typing import Optional, Dict, Tuple
import pandas as pd
import numpy as np
from datetime import datetime

from .repository import FinancialDataRepository

logger = logging.getLogger(__name__)

class StressIndexService:
    """
    重構後的服務層，負責所有壓力指標的計算。
    現在所有涉及 I/O 的操作都是非同步的。
    """
    def __init__(self, repository: FinancialDataRepository):
        self.repository = repository
        self.STRESS_INDEX_WEIGHTS = {
            'sofr_dev': 0.25, 'spread_inv': 0.10, 'hys_inv': 0.10,
            'gross_pos': 0.05, 'move': 0.25, 'vix': 0.15, 'pos_res_ratio': 0.10
        }
        self.ROLLING_WINDOW_DAYS = 252
        self.SMOOTHING_WINDOW = 5
        self.POS_RES_RATIO_THRESHOLD = 90

    async def calculate_full_metrics(self, start_date: str, end_date: str) -> Tuple[Optional[pd.DataFrame], bool]:
        """
        非同步計算所有指標。
        返回一個包含計算結果 DataFrame 的元組，以及一個布林值表示資料是否已就緒。
        """
        logger.info("服務層：開始從倉儲異步獲取所有基礎數據...")
        # get_all_series 現在會返回數據和一個表示快取是否完全命中的標誌
        valid_series, all_data_ready = await self.repository.get_all_series(start_date, end_date)

        # 如果任何數據缺失（正在後台抓取），則立即返回，告知上層資料尚未就緒
        if not all_data_ready:
            logger.info("服務層：數據尚未完全快取，計算中止。")
            return None, False

        if not valid_series:
            logger.warning("服務層：倉儲未返回任何有效的數據序列。")
            return None, True

        df = pd.concat(valid_series.values(), axis=1, join='outer').ffill()
        if df.empty:
            return None, True

        # --- 後續的 pandas 計算邏輯保持不變 ---
        df['spread_10y2y'] = df.get('dgs10') - df.get('dgs2')
        df['sofr_ma60'] = df['sofr'].rolling(window=60, min_periods=30).mean()
        df['sofr_dev'] = df['sofr'] - df['sofr_ma60']
        df['pos_res_ratio'] = df.get('dealer_net_positions') / df.get('wresbal', 0).replace(0, np.nan)

        perc_ranks = pd.DataFrame(index=df.index)
        min_periods_rank = int(self.ROLLING_WINDOW_DAYS * 0.6)
        component_map = {
            'sofr_dev': 'sofr_dev', 'spread_inv': 'spread_10y2y',
            'hys_inv': 'us_high_yield_spread', 'gross_pos': 'dealer_net_positions',
            'vix': 'vix', 'pos_res_ratio': 'pos_res_ratio'
        }
        for name, col in component_map.items():
            if col in df and df[col].notna().sum() >= min_periods_rank:
                rank_pct = df[col].rolling(window=self.ROLLING_WINDOW_DAYS, min_periods=min_periods_rank).rank(pct=True)
                perc_ranks[name] = 1.0 - rank_pct if name in ['spread_inv', 'hys_inv'] else rank_pct

        active_weights = {k: v for k, v in self.STRESS_INDEX_WEIGHTS.items() if k in perc_ranks.columns and perc_ranks[k].notna().any()}
        if not active_weights:
            df['dealer_stress_index'] = np.nan
            return df, True

        total_weight = sum(active_weights.values())
        weights_normalized = {k: v / total_weight for k, v in active_weights.items()}

        ratio_high_condition = (df['pos_res_ratio'] >= self.POS_RES_RATIO_THRESHOLD).astype(float).fillna(0.0)
        combined_score = pd.Series(0.0, index=df.index)
        for name, weight in weights_normalized.items():
            rank_series = perc_ranks[name].fillna(0.5)
            if name == 'pos_res_ratio':
                combined_score += rank_series * ratio_high_condition * weight
            else:
                combined_score += rank_series * weight

        df['dealer_stress_index_raw'] = (combined_score * 100).clip(0, 100)

        if self.SMOOTHING_WINDOW > 1:
            min_periods_smooth = max(1, int(self.SMOOTHING_WINDOW * 0.5))
            df['dealer_stress_index'] = df['dealer_stress_index_raw'].rolling(
                window=self.SMOOTHING_WINDOW, min_periods=min_periods_smooth, center=True
            ).mean().clip(0, 100)
        else:
            df['dealer_stress_index'] = df['dealer_stress_index_raw']

        base_series = df['dealer_stress_index'].dropna()
        if len(base_series) > 26:
            ema_fast = base_series.ewm(span=12, adjust=False).mean()
            ema_slow = base_series.ewm(span=26, adjust=False).mean()
            df['macd_line'] = (ema_fast - ema_slow).reindex(df.index)
            df['macd_signal_line'] = df['macd_line'].ewm(span=9, adjust=False).mean()
            df['macd_hist'] = df['macd_line'] - df['macd_signal_line']
        else:
            df[['macd_line', 'macd_signal_line', 'macd_hist']] = np.nan, np.nan, np.nan

        return df, True

    async def check_for_updates(self) -> Optional[Dict]:
        """
        (此函式目前未被使用，但保留其異步結構以備未來之需)
        異步檢查是否有新數據點。
        """
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - pd.DateOffset(days=30)).strftime('%Y-%m-%d')

        full_metrics_df, data_ready = await self.calculate_full_metrics(start_date, end_date)

        if not data_ready or full_metrics_df is None or full_metrics_df.empty:
            return None

        # ... 後續邏輯與之前相同 ...
        return None
