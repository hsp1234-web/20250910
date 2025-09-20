# -*- coding: utf-8 -*-
"""
存放所有分析腳本所需的設定參數。
此檔案內容移植自 `一級交易pro.py` 腳本中的 PROJECT_CONFIG 字典。
"""

import logging

# 專案設定字典
# 移植自 `一級交易pro.py`
PROJECT_CONFIG = {
  # --- 基本設定 ---
  'project_name': '一級交易商壓力分析 (模組化)',
  'version': '1.9', # 更新版本號
  'fred_api_key': "77b0a570c6a17007e4f5af229c2aecc9",
  'timezone': 'Asia/Taipei',
  'log_level': logging.INFO,
  # --- 日期相關 ---
  'default_start_date': "2017-01-01",
  'fallback_start_date': "2018-01-01",
  # --- 圖表設定 ---
  'trend_plot_days': 60,
  # --- 長天期公債 ETF 設定 ---
  'enable_lt_bond_etf_plot': True,
  'lt_bond_etf_ticker': "TLT",
  # --- NY Fed API URLs (分行顯示) ---
  'ny_fed_positions_urls': [
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
  ],
  # --- 舊版 SBP 加總邏輯 ---
  'sbp2013_cols_to_sum': [
      'PDPUSGCS3LNOP', 'PDPUSGCS36NOP', 'PDPUSGCS611NOP', 'PDPUSGCSM11NOP'
  ],
  'sbp2001_cols_to_sum': ['PDPUSGCS5LNOP', 'PDPUSGCS5MNOP'],
  # --- 壓力指數計算設定 ---
  'rolling_window_days': 252,
  'weights': {
      'sofr_dev': 0.35, 'spread_inv': 0.10, 'gross_pos': 0.05,
      'move': 0.25, 'vix': 0.15, 'pos_res_ratio': 0.10
  },
  # --- 指數平滑與著色 ---
  'smoothing_window_stress_index': 5,
  'threshold_high_stress_color': 55,
  # --- 持有/準備金 比率著色閾值 ---
  'threshold_ratio_color': 90,
  # --- MACD 設定 ---
  'enable_macd_momentum_plot': True,
  'macd_params': {'fast': 12, 'slow': 26, 'signal': 9},
  'macd_colors': {'blue': "#6495ED", 'green': "#3CB371", 'red': "#B22222"}
}
