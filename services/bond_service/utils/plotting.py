# -*- coding: utf-8 -*-
"""
繪圖模組 (Plotting)

功能：
- 包含所有生成圖表的函式。
- 支援多種輸出格式，特別是 'base64' 以便透過 API 傳輸。
- 此模組的邏輯主要移植自 `一級交易pro.py` 的 Cell 2, 9, 10。
"""
import logging
import io
import base64
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg') # 使用非互動式後端，這在伺服器環境中至關重要
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from datetime import datetime

# 從設定檔導入專案設定
from services.bond_service.config import PROJECT_CONFIG

# 設定日誌
logger = logging.getLogger(__name__)


def plot_results_as_base64(final_df: pd.DataFrame, config: dict = PROJECT_CONFIG) -> str:
    """
    產生基於最終數據的時間序列圖表集合 (5x2 網格佈局)，並回傳 Base64 編碼。
    (移植自 Cell 2 和 Cell 9 的邏輯)

    Args:
        final_df (pd.DataFrame): 包含所有計算指標的最終 DataFrame。
        config (dict): 專案設定字典。

    Returns:
        str: Base64 編碼的 PNG 圖片字串，如果無法繪圖則返回空字串。
    """
    logger.info("正在生成時間序列圖 (5x2 佈局)...")
    fig, axes = plt.subplots(nrows=5, ncols=2, figsize=(14, 20), sharex=True)

    try:
        # --- 準備參數和數據可用性檢查 ---
        params = {
            'smoothing_window': config.get('smoothing_window_stress_index', 5),
            'threshold_stress': config.get('threshold_high_stress_color', 55),
            'threshold_ratio': config.get('threshold_ratio_color', 90),
            'enable_macd': config.get('enable_macd_momentum_plot', False),
            'macd_p': config.get('macd_params', {}),
            'macd_c': config.get('macd_colors', {}),
            'enable_etf': config.get('enable_lt_bond_etf_plot', False),
            'etf_ticker': config.get('lt_bond_etf_ticker', '').strip().upper()
        }

        etf_col = f"ETF_{params['etf_ticker']}_Price" if params['etf_ticker'] else None

        is_ok = {
            'SOFR': 'SOFR' in final_df and final_df['SOFR'].notna().any(),
            'Spread': 'Spread_10Y2Y' in final_df and final_df['Spread_10Y2Y'].notna().any(),
            'MOVE': 'Volatility_Index' in final_df and final_df['Volatility_Index'].notna().any(),
            'VIX': 'VIX' in final_df and final_df['VIX'].notna().any(),
            'Dealer Pos': 'Total_Gross_Positions_Millions' in final_df and final_df['Total_Gross_Positions_Millions'].notna().any(),
            'Reserves': 'Reserves' in final_df and final_df['Reserves'].notna().any(),
            'Stress Index': 'Dealer_Stress_Index' in final_df and final_df['Dealer_Stress_Index'].notna().any(),
            'Ratio': 'Pos_Res_Ratio' in final_df and final_df['Pos_Res_Ratio'].notna().any(),
            'MACD': params['enable_macd'] and 'Stress_Index_MACD_Hist' in final_df and final_df['Stress_Index_MACD_Hist'].notna().any(),
            'ETF': params['enable_etf'] and etf_col and etf_col in final_df and final_df[etf_col].notna().any()
        }

        axes_map = [
            (axes[0, 0], 'SOFR', lambda ax, df: ax.plot(df.index, df['SOFR'], label='SOFR (%)', color='purple')),
            (axes[0, 1], 'Spread', lambda ax, df: ax.plot(df.index, df['Spread_10Y2Y']*100, label='10Y-2Y Spread (BPS)', color='orange')),
            (axes[1, 0], 'MOVE', lambda ax, df: ax.plot(df.index, df['Volatility_Index'], label='MOVE Index', color='#00AEAE')),
            (axes[1, 1], 'VIX', lambda ax, df: ax.plot(df.index, df['VIX'], label='VIX Index', color='magenta')),
            (axes[2, 0], 'Dealer Pos', lambda ax, df: ax.plot(df.index, df['Total_Gross_Positions_Millions']/1000, label='Dealer Pos (Bil USD)', color='green')),
            (axes[2, 1], 'Reserves', lambda ax, df: ax.plot(df.index, df['Reserves']/1000000, label='Reserves (Tril USD)', color='goldenrod')),
            (axes[3, 0], 'Stress Index', lambda ax, df: ax.plot(df.index, df['Dealer_Stress_Index'], label='Stress Index', color='red')),
            (axes[3, 1], 'Ratio', lambda ax, df: ax.plot(df.index, df['Pos_Res_Ratio'], label='Pos/Reserves Ratio', color='#FFBB66')),
            (axes[4, 0], 'MACD', lambda ax, df: ax.bar(df.index, df['Stress_Index_MACD_Hist'], color=df['Stress_Index_MACD_Color'], width=1.0)),
            (axes[4, 1], 'ETF', lambda ax, df: ax.plot(df.index, df[etf_col], label=f"{params['etf_ticker']} Price", color='#0077CC')),
        ]

        plot_count = 0
        for ax, name, plot_func in axes_map:
            if is_ok.get(name):
                plot_func(ax, final_df)
                ax.legend(loc='upper left', fontsize='small')
                ax.set_title(name, fontsize='medium')
                plot_count += 1
            else:
                ax.set_visible(False)

        if plot_count == 0:
            logger.warning("沒有任何有效的數據可以生成時間序列圖。")
            return ""

        fig.suptitle("Systemic Risk Indicators & Stress Index", fontsize=16, fontweight='bold')
        fig.tight_layout(rect=[0, 0.03, 1, 0.97])

        # 轉換為 Base64
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        image_base64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        logger.info("時間序列圖已成功轉換為 Base64。")
        return f"data:image/png;base64,{image_base64}"

    except Exception as e:
        logger.error(f"生成時間序列圖時發生錯誤: {e}", exc_info=True)
        return ""
    finally:
        plt.close(fig) # 確保關閉圖形以釋放記憶體


def generate_all_plots(final_df: pd.DataFrame) -> dict:
    """
    生成所有需要的圖表並以字典形式返回 Base64 編碼。

    Args:
        final_df (pd.DataFrame): 包含所有計算結果的最終 DataFrame。

    Returns:
        dict: 一個字典，鍵是圖表名稱，值是 Base64 編碼的圖片字串。
    """
    plots = {}
    logger.info("開始生成所有圖表...")

    # 1. 生成主要時間序列圖
    plots['main_timeseries'] = plot_results_as_base64(final_df)

    # 後續可以加入儀表板和趨勢圖的生成
    # plot_gemini_gauge_mpl 和 plot_trend_colored 的邏輯可以類似地添加到這裡

    logger.info("所有圖表生成完畢。")
    return plots
