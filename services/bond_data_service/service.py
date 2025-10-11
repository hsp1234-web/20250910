# poc/bond_data_service_v2/service.py

import logging
from typing import Optional, Dict
from datetime import datetime
import pandas as pd
import numpy as np
from cachetools import TTLCache, cached

from .repository import FinancialDataRepository

logger = logging.getLogger(__name__)

def cache_key(service, start_date, end_date):
    return (start_date, end_date)

class StressIndexService:
    """
    服務的「大腦」，負責所有壓力指標的計算以及相關的業務邏輯。
    它與 API 層完全解耦。
    """
    # 修正：將快取移至類別層級以進行除錯。
    # 這意味著所有實例將共享同一個快取，並能繞過在 @cached 中使用 lambda 的問題。
    metrics_cache = TTLCache(maxsize=10, ttl=300)

    def __init__(self, repository: FinancialDataRepository):
        self.repository = repository
        self.last_broadcasted_timestamp: Optional[pd.Timestamp] = None
        # 常數
        self.STRESS_INDEX_WEIGHTS = {
            'sofr_dev': 0.25, 'spread_inv': 0.10, 'hys_inv': 0.10,
            'gross_pos': 0.05, 'move': 0.25, 'vix': 0.15, 'pos_res_ratio': 0.10
        }
        self.ROLLING_WINDOW_DAYS = 252
        self.SMOOTHING_WINDOW = 5
        self.POS_RES_RATIO_THRESHOLD = 90 # 補上缺失的常數

    @cached(cache=metrics_cache, key=cache_key)
    def calculate_full_metrics(self, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        # (此處省略 calculate_full_metrics 的完整程式碼，因為它很長且未變動)
        logger.info("服務層：開始從倉儲獲取所有基礎數據...")
        indicator_list = [
            "sofr", "dgs10", "dgs2", "vix", "us_high_yield_spread",
            "dealer_net_positions", "wresbal", "rrp",
            "dealer_long_term_positions", "dealer_short_term_positions"
        ]
        all_series = {
            indicator: self.repository.get_series(indicator, start_date, end_date)
            for indicator in indicator_list
        }
        valid_series = {k: v for k, v in all_series.items() if v is not None and not v.empty}
        if not valid_series:
            return None

        df = pd.concat(valid_series.values(), axis=1, join='outer').ffill()
        if df.empty:
            return None

        if 'dgs10' in df and 'dgs2' in df:
            df['spread_10y2y'] = df['dgs10'] - df['dgs2']
        else:
            df['spread_10y2y'] = np.nan
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
            else:
                perc_ranks[name] = np.nan

        active_weights = {k: v for k, v in self.STRESS_INDEX_WEIGHTS.items() if k in perc_ranks.columns and perc_ranks[k].notna().any()}
        if not active_weights:
            df['dealer_stress_index'] = np.nan
            return df

        total_weight = sum(active_weights.values())
        weights_normalized = {k: v / total_weight for k, v in active_weights.items()}

        # 修正：恢復舊的、帶有特殊條件的加權邏輯
        ratio_high_condition = (df['pos_res_ratio'] >= self.POS_RES_RATIO_THRESHOLD).astype(float).fillna(0.0)
        combined_score = pd.Series(0.0, index=df.index)
        for name, weight in weights_normalized.items():
            rank_series = perc_ranks[name].fillna(0.5)
            if name == 'pos_res_ratio':
                combined_score += rank_series * ratio_high_condition * weight
            else:
                combined_score += rank_series * weight

        df['dealer_stress_index_raw'] = (combined_score * 100).clip(0, 100)

        # 修正：恢復舊的、正確的滾動平滑邏輯
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
            df[['macd_line', 'macd_signal_line', 'macd_hist']] = np.nan

        return df

    def check_for_updates(self) -> Optional[Dict]:
        """
        檢查是否有新數據點，如果有，則返回廣播所需的 payload。
        此方法不執行廣播，只返回數據。
        """
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - pd.DateOffset(days=30)).strftime('%Y-%m-%d')

        full_metrics_df = self.calculate_full_metrics(start_date, end_date)

        if full_metrics_df is None or full_metrics_df.empty:
            return None

        valid_data = full_metrics_df.dropna(subset=['dealer_stress_index'])
        if valid_data.empty:
            return None

        latest_data_point = valid_data.iloc[-1]
        latest_timestamp = latest_data_point.name

        if self.last_broadcasted_timestamp is None or latest_timestamp > self.last_broadcasted_timestamp:
            logger.info(f"服務層：偵測到新數據點 (時間戳: {latest_timestamp})，將返回 payload。")

            payload = {
                'date': latest_timestamp.isoformat(),
                'dealer_stress_index': latest_data_point.get('dealer_stress_index'),
                'macd_line': latest_data_point.get('macd_line'),
                'macd_signal_line': latest_data_point.get('macd_signal_line'),
                'macd_hist': latest_data_point.get('macd_hist')
            }
            payload_clean = {k: (None if pd.isna(v) else v) for k, v in payload.items()}

            self.last_broadcasted_timestamp = latest_timestamp
            return payload_clean

        return None