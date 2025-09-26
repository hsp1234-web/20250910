# services/bond_data_service/charting.py

import pandas as pd
import plotly.graph_objects as go
from typing import Optional
import numpy as np

# --- 圖表設定 ---
# 共享的圖表標籤，確保所有圖表風格統一
CHART_LABELS = {
    "dealer_stress_index": "一級交易商壓力指數",
    "sofr": "擔保隔夜融資利率 (SOFR)",
    "spread_10y2y": "10-2年期公債利差",
    "move_index": "美林選擇權波動率預估 (MOVE)",
    "vix": "CBOE 波動率指數 (VIX)",
    "dealer_positions": "一級交易商公債持有量",
    "wresbal": "聯邦儲備銀行準備金餘額",
    "pos_res_ratio": "持有量/準備金比率",
    "etf_tlt": "iShares 20+年期公債 ETF (TLT)",
    "macd": "壓力指數 MACD 動能",
    "gauge": "壓力儀表板",
    "trend": "近期壓力趨勢"
}

def get_chart_title(indicator_id: str) -> str:
    """獲取圖表的標準化標題"""
    return CHART_LABELS.get(indicator_id, indicator_id.upper())

def generate_chart_response(fig: go.Figure):
    """將 Plotly 圖表轉換為圖片位元組"""
    if not isinstance(fig, go.Figure):
        return None
    return fig.to_image(format="jpeg", width=800, height=500, scale=2)

# --- 圖表工廠函式 ---

def plot_sofr(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製 SOFR 圖表"""
    if 'sofr' not in df or df['sofr'].dropna().empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['sofr'], name="SOFR", mode='lines', line=dict(color='purple')))
    if 'sofr_ma60' in df and df['sofr_ma60'].notna().any():
        fig.add_trace(go.Scatter(x=df.index, y=df['sofr_ma60'], name="60日移動平均", mode='lines', line=dict(color='lightblue', dash='dash')))
    fig.update_layout(title=get_chart_title('sofr'), xaxis_title="日期", yaxis_title="利率 (%)", template="plotly_white")
    return fig

def plot_spread_10y2y(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製 10-2年期公債利差圖表"""
    col = 'spread_10y2y'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    # 轉換為基點 (BPS)
    bps_values = df[col] * 100
    fig.add_trace(go.Scatter(x=df.index, y=bps_values, name="利差", mode='lines', line=dict(color='orange')))
    fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="grey")
    fig.update_layout(title=get_chart_title(col), xaxis_title="日期", yaxis_title="基點 (BPS)", template="plotly_white")
    return fig

def plot_move_index(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製 MOVE 指數圖表"""
    col = 'move_index'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df[col], name="MOVE", mode='lines', line=dict(color='#00AEAE')))
    fig.update_layout(title=get_chart_title(col), xaxis_title="日期", yaxis_title="指數值", template="plotly_white")
    return fig

def plot_vix(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製 VIX 指數圖表"""
    col = 'vix'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df[col], name="VIX", mode='lines', line=dict(color='magenta')))
    fig.update_layout(title=get_chart_title(col), xaxis_title="日期", yaxis_title="指數值", template="plotly_white")
    return fig

def plot_dealer_positions(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製一級交易商持有量圖表"""
    col = 'dealer_positions'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    # 從百萬美元轉換為億美元
    bil_values = df[col] / 1000
    fig.add_trace(go.Scatter(x=df.index, y=bil_values, name="持有量", mode='lines', line=dict(color='green')))
    fig.update_layout(title=get_chart_title(col), xaxis_title="日期", yaxis_title="十億美元 (Billion USD)", template="plotly_white")
    return fig

def plot_reserves(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製總準備金餘額圖表"""
    col = 'wresbal'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    # 從百萬美元轉換為兆美元
    tril_values = df[col] / 1000000
    fig.add_trace(go.Scatter(x=df.index, y=tril_values, name="準備金", mode='lines', line=dict(color='goldenrod')))
    fig.update_layout(title=get_chart_title(col), xaxis_title="日期", yaxis_title="兆美元 (Trillion USD)", template="plotly_white")
    return fig

def plot_etf_tlt(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製 TLT ETF 價格圖表"""
    # 假設 ETF Ticker 為 TLT
    col = 'etf_tlt_price' # 假設欄位名稱，未來可改為動態
    if col not in df or df[col].dropna().empty:
        # 如果找不到，也可能是因為計算模組中未加入
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df[col], name="TLT 價格", mode='lines', line=dict(color='#0077CC')))
    fig.update_layout(title=get_chart_title('etf_tlt'), xaxis_title="日期", yaxis_title="價格 (USD)", template="plotly_white")
    return fig

def plot_pos_res_ratio(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製持有量/準備金比率圖表"""
    col = 'pos_res_ratio'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df[col], name="比率", mode='lines', line=dict(color='#FFBB66')))
    fig.add_hline(y=90, line_width=1, line_dash="dash", line_color="red", annotation_text="90 閾值")
    fig.update_layout(title=get_chart_title(col), xaxis_title="日期", yaxis_title="比率值", template="plotly_white")
    return fig

def plot_stress_index(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製壓力指數圖表"""
    col = 'dealer_stress_index'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df[col], mode='lines', name=get_chart_title(col)))
    fig.add_hrect(y0=60, y1=80, line_width=0, fillcolor="yellow", opacity=0.2, annotation_text="高壓力區", annotation_position="bottom right")
    fig.add_hrect(y0=80, y1=100, line_width=0, fillcolor="red", opacity=0.2, annotation_text="極端壓力區", annotation_position="top right")
    fig.update_layout(title=get_chart_title(col), xaxis_title="日期", yaxis_title="指數 (0-100)", template="plotly_white", yaxis_range=[0, 100])
    return fig

def plot_macd(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製壓力指數的 MACD 圖表"""
    hist_col, line_col, signal_col = 'macd_hist', 'macd_line', 'macd_signal_line'
    if hist_col not in df or df[hist_col].dropna().empty:
        return None

    # 根據趨勢為柱狀圖上色
    hist_diff = df[hist_col].diff()
    colors = np.where(hist_diff > 0, '#6495ED', '#B22222') # 上升為藍，下降為紅
    colors[df[hist_col] < 0] = np.where(hist_diff[df[hist_col] < 0] > 0, '#3CB371', '#B22222') # 負值部分，上升為綠

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df.index, y=df[hist_col], name='Histogram', marker_color=colors))
    fig.add_trace(go.Scatter(x=df.index, y=df[line_col], name='MACD Line', mode='lines', line=dict(color='black', width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df[signal_col], name='Signal Line', mode='lines', line=dict(color='orange', width=1)))
    fig.update_layout(title=get_chart_title('macd'), xaxis_title="日期", yaxis_title="動能", template="plotly_white")
    return fig

def plot_gauge(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製壓力儀表板"""
    col = 'dealer_stress_index'
    if col not in df or df[col].dropna().empty:
        return None
    latest_value = df[col].dropna().iloc[-1]

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=latest_value,
        title={'text': get_chart_title('gauge')},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': "darkblue"},
            'steps': [
                {'range': [0, 60], 'color': "lightgreen"},
                {'range': [60, 80], 'color': "yellow"},
                {'range': [80, 100], 'color': "red"}],
        }))
    return fig

def plot_trend(df: pd.DataFrame, days: int = 60) -> Optional[go.Figure]:
    """繪製近期壓力趨勢圖"""
    col = 'dealer_stress_index'
    if col not in df or df[col].dropna().empty:
        return None

    trend_df = df.tail(days)
    if trend_df.empty:
        return None

    fig = go.Figure()
    # 繪製基礎線
    fig.add_trace(go.Scatter(x=trend_df.index, y=trend_df[col], mode='lines', name="趨勢", line=dict(color='grey')))

    # 根據閾值分段著色
    for y_start, y_end, color in [(0, 60, 'green'), (60, 80, 'orange'), (80, 100, 'red')]:
        fig.add_trace(go.Scatter(
            x=trend_df.index,
            y=trend_df[col].where((trend_df[col] >= y_start) & (trend_df[col] < y_end)),
            mode='lines',
            line=dict(color=color, width=3),
            showlegend=False
        ))

    fig.update_layout(title=f"{get_chart_title('trend')} (最近 {days} 天)", xaxis_title="日期", yaxis_title="指數 (0-100)", template="plotly_white", yaxis_range=[0, 100])
    return fig