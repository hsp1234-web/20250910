# -*- coding: utf-8 -*-
"""
文字報告生成模組 (Reporting)

功能：
- 根據最終計算的壓力指數，生成文字分析報告。
- 包括與歷史事件的對比和市場情境分析。
- 此模組的邏輯主要移植自 `一級交易pro.py` 的 Cell 11。
"""
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

def generate_text_report(final_df: pd.DataFrame) -> str:
    """
    根據最終 DataFrame 生成文字分析報告。

    Args:
        final_df (pd.DataFrame): 包含所有計算結果的最終 DataFrame。

    Returns:
        str: 格式化的文字分析報告。
    """
    logger.info("開始生成文字分析報告...")
    if 'Dealer_Stress_Index' not in final_df.columns or final_df['Dealer_Stress_Index'].isna().all():
        logger.warning("final_df 中缺少有效的 'Dealer_Stress_Index'，無法生成報告。")
        return "無法生成報告：缺少有效的壓力指數數據。"

    stress_series = final_df['Dealer_Stress_Index'].dropna()
    if stress_series.empty:
        latest_stress_value = np.nan
        latest_stress_date = "N/A"
    else:
        latest_stress_value = stress_series.iloc[-1]
        latest_stress_date = stress_series.index[-1].strftime('%Y-%m-%d')

    report_lines = []

    # --- 1. 歷史對比 ---
    report_lines.append("--- 歷史對比與提醒 ---")
    report_lines.append(f"當前 ({latest_stress_date}) 壓力指數: {latest_stress_value:.2f}\n")

    if pd.notna(latest_stress_value):
        historical_peaks = {
            "雷曼兄弟時期 (~2008)": 95,
            "新冠疫情衝擊 (2020)": 80,
            "回購利率飆升 (2019)": 65,
        }
        for event, peak_value in historical_peaks.items():
            if latest_stress_value >= peak_value * 0.95:
                comparison_text = f"警示：已達到或超過 {event} 的參考水平 (約 {peak_value})。"
            elif latest_stress_value >= peak_value * 0.8:
                comparison_text = f"注意：已接近 {event} 的參考水平 (約 {peak_value})。"
            else:
                comparison_text = f"目前低於 {event} 的參考水平 (約 {peak_value})。"
            report_lines.append(f"- {comparison_text}")

    # --- 2. 情境分析 ---
    scenario_analysis = """
--- 市場壓力情境分析與一般性考量 ---

>>> 重要免責聲明 <<<
以下內容基於壓力指數的假設性變動，提供一般性的市場觀察和原則性考量，
不構成任何形式的投資建議。市場實際表現受多重複雜因素影響，
任何投資決策請務必諮詢合格的專業財務顧問，並進行獨立判斷。

若壓力指數持續上升:
  - 債券市場：通常伴隨避險情緒升溫，可能導致投資者湧向美國公債，壓低長天期公債殖利率。信用利差可能擴大。
  - 股票市場：波動性（如VIX）通常會顯著升高，可能導致股市普遍下跌，尤其是對利率敏感的成長股。
  - 策略考量：重新評估風險敞口，關注資產質量，考慮維持較高現金水平。

若壓力指數持續下降:
  - 債券市場：避險情緒降溫，資金可能流出公債，導致殖利率上升。信用利差可能收窄。
  - 股票市場：波動性可能降低，投資者風險偏好提升，可能帶動股市上漲。
  - 策略考量：評估增持風險資產的機會，關注市場風格是否輪動，考慮對投資組合進行再平衡。
"""
    report_lines.append(scenario_analysis)

    logger.info("文字分析報告生成完畢。")
    return "\n".join(report_lines)
