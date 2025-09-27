# services/bond_data_service/charting.py

import pandas as pd
import plotly.graph_objects as go
from typing import Optional, Literal
import numpy as np

# --- 圖表設定 (英文) ---
# 共享的圖表標籤，確保所有圖表風格統一
CHART_LABELS = {
    "dealer_stress_index": "Primary Dealer Stress Index (Composite)",
    "sofr": "Secured Overnight Financing Rate (SOFR)",
    "spread_10y2y": "10-2 Year US Treasury Spread",
    "move_index": "MOVE Index (Bond Market Volatility)",
    "vix": "CBOE Volatility Index (VIX)",
    "dealer_net_positions": "Primary Dealer Net US Treasury Positions",
    "wresbal": "Total Reserve Balances",
    "pos_res_ratio": "Positions to Reserves Ratio",
    "etf_tlt": "iShares 20+ Year Treasury Bond ETF (TLT)",
    "macd": "Stress Index MACD Momentum",
    "gauge": "Stress Gauge",
    "trend": "Recent Stress Trend",
    "ofr_fci": "OFR Financial Stress Index",
    "us_high_yield_spread": "US High-Yield Spread (BofA)",
    "dealer_short_term_positions": "Primary Dealer Short-Term Treasury Positions",
    "dealer_long_term_positions": "Primary Dealer Long-Term Treasury Positions",
}

def get_chart_title(indicator_id: str) -> str:
    """獲取圖表的標準化標題"""
    return CHART_LABELS.get(indicator_id, indicator_id.replace('_', ' ').title())

def generate_chart_response(fig: go.Figure):
    """將 Plotly 圖表轉換為圖片位元組"""
    if not isinstance(fig, go.Figure):
        return None
    return fig.to_image(format="jpeg", width=800, height=500, scale=2)

def plot_not_available(chart_name: str) -> go.Figure:
    """
    生成一個表示「圖表暫未提供」或「數據不足」的佔位圖。
    """
    fig = go.Figure()
    fig.add_annotation(
        text=f"Chart Failed to Load<br><b>'{chart_name}'</b><br>Insufficient data or service error.",
        xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=20, color="grey")
    )
    fig.update_layout(
        xaxis_visible=False,
        yaxis_visible=False,
        plot_bgcolor='rgba(240,240,240,0.95)',
        margin=dict(t=20, b=20, l=20, r=20)
    )
    return fig

# --- 圖表工廠函式 (已全部英文化) ---

def plot_sofr(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製 SOFR 圖表"""
    if 'sofr' not in df or df['sofr'].dropna().empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['sofr'], name="SOFR", mode='lines', line=dict(color='purple')))
    if 'sofr_ma60' in df and df['sofr_ma60'].notna().any():
        fig.add_trace(go.Scatter(x=df.index, y=df['sofr_ma60'], name="60-Day MA", mode='lines', line=dict(color='lightblue', dash='dash')))
    fig.update_layout(title=get_chart_title('sofr'), xaxis_title="Date", yaxis_title="Rate (%)", template="plotly_white")
    return fig

def plot_spread_10y2y(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製 10-2年期公債利差圖表"""
    col = 'spread_10y2y'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    bps_values = df[col] * 100
    fig.add_trace(go.Scatter(x=df.index, y=bps_values, name="Spread", mode='lines', line=dict(color='orange')))
    fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="grey")
    fig.update_layout(title=get_chart_title(col), xaxis_title="Date", yaxis_title="Basis Points (BPS)", template="plotly_white")
    return fig

def plot_move_index(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製 MOVE 指數圖表"""
    col = 'move_index'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df[col], name="MOVE", mode='lines', line=dict(color='#00AEAE')))
    fig.update_layout(title=get_chart_title(col), xaxis_title="Date", yaxis_title="Index Value", template="plotly_white")
    return fig

def plot_vix(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製 VIX 指數圖表"""
    col = 'vix'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df[col], name="VIX", mode='lines', line=dict(color='magenta')))
    fig.update_layout(title=get_chart_title(col), xaxis_title="Date", yaxis_title="Index Value", template="plotly_white")
    return fig

def plot_dealer_positions(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製一級交易商淨持有量圖表"""
    col = 'dealer_net_positions' # 修正: 從 'dealer_positions' 改為 'dealer_net_positions'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    bil_values = df[col] / 1000
    fig.add_trace(go.Scatter(x=df.index, y=bil_values, name="Net Positions", mode='lines', line=dict(color='green')))
    fig.update_layout(title=get_chart_title(col), xaxis_title="Date", yaxis_title="Billions USD", template="plotly_white")
    return fig

def plot_us_high_yield_spread(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製美國高收益債利差圖表"""
    col = 'us_high_yield_spread'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df[col], name="High-Yield Spread", mode='lines', line=dict(color='#FF6347')))
    fig.update_layout(title=get_chart_title(col), xaxis_title="Date", yaxis_title="Percentage (%)", template="plotly_white")
    return fig

def plot_dealer_positions_by_maturity(df: pd.DataFrame, maturity: Literal['short', 'long']) -> Optional[go.Figure]:
    """
    根據期限繪製一級交易商的公債部位 (短期或長期)。
    """
    if maturity == 'short':
        col = 'dealer_short_term_positions'
        color = '#4682B4' # SteelBlue
    elif maturity == 'long':
        col = 'dealer_long_term_positions'
        color = '#32CD32' # LimeGreen
    else:
        return None

    if col not in df or df[col].dropna().empty:
        return None

    fig = go.Figure()
    bil_values = df[col] / 1000
    chart_title = get_chart_title(col)
    fig.add_trace(go.Scatter(x=df.index, y=bil_values, name=chart_title, mode='lines', line=dict(color=color)))
    fig.update_layout(title=chart_title, xaxis_title="Date", yaxis_title="Billions USD", template="plotly_white")
    return fig

def plot_reserves(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製總準備金餘額圖表"""
    col = 'wresbal'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    tril_values = df[col] / 1000000
    fig.add_trace(go.Scatter(x=df.index, y=tril_values, name="Reserves", mode='lines', line=dict(color='goldenrod')))
    fig.update_layout(title=get_chart_title(col), xaxis_title="Date", yaxis_title="Trillions USD", template="plotly_white")
    return fig

def plot_etf_tlt(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製 TLT ETF 價格圖表"""
    col = 'etf_tlt_price'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df[col], name="TLT Price", mode='lines', line=dict(color='#0077CC')))
    fig.update_layout(title=get_chart_title('etf_tlt'), xaxis_title="Date", yaxis_title="Price (USD)", template="plotly_white")
    return fig

def plot_pos_res_ratio(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製持有量/準備金比率圖表"""
    col = 'pos_res_ratio'
    if col not in df or df[col].dropna().empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df[col], name="Ratio", mode='lines', line=dict(color='#FFBB66')))
    fig.add_hline(y=90, line_width=1, line_dash="dash", line_color="red", annotation_text="90 Threshold")
    fig.update_layout(title=get_chart_title(col), xaxis_title="Date", yaxis_title="Ratio Value", template="plotly_white")
    return fig

def plot_stress_index(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製壓力指數圖表"""
    col = 'dealer_stress_index'
    if col not in df or df[col].dropna().empty:
        title = get_chart_title('ofr_fci') if 'ofr_fci' in CHART_LABELS else get_chart_title(col)
    else:
        title = get_chart_title(col)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df[col], mode='lines', name=title))
    fig.add_hrect(y0=60, y1=80, line_width=0, fillcolor="yellow", opacity=0.2, annotation_text="High Stress", annotation_position="bottom right")
    fig.add_hrect(y0=80, y1=100, line_width=0, fillcolor="red", opacity=0.2, annotation_text="Extreme Stress", annotation_position="top right")
    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Index (0-100)", template="plotly_white", yaxis_range=[0, 100])
    return fig

def plot_macd(df: pd.DataFrame) -> Optional[go.Figure]:
    """繪製壓力指數的 MACD 圖表"""
    hist_col, line_col, signal_col = 'macd_hist', 'macd_line', 'macd_signal_line'
    if hist_col not in df or df[hist_col].dropna().empty:
        return None

    hist_diff = df[hist_col].diff()
    colors = np.where(hist_diff > 0, '#6495ED', '#B22222')
    colors[df[hist_col] < 0] = np.where(hist_diff[df[hist_col] < 0] > 0, '#3CB371', '#B22222')

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df.index, y=df[hist_col], name='Histogram', marker_color=colors))
    fig.add_trace(go.Scatter(x=df.index, y=df[line_col], name='MACD Line', mode='lines', line=dict(color='black', width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df[signal_col], name='Signal Line', mode='lines', line=dict(color='orange', width=1)))
    fig.update_layout(title=get_chart_title('macd'), xaxis_title="Date", yaxis_title="Momentum", template="plotly_white")
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
    fig.add_trace(go.Scatter(x=trend_df.index, y=trend_df[col], mode='lines', name="Trend", line=dict(color='grey')))

    for y_start, y_end, color in [(0, 60, 'green'), (60, 80, 'orange'), (80, 100, 'red')]:
        fig.add_trace(go.Scatter(
            x=trend_df.index,
            y=trend_df[col].where((trend_df[col] >= y_start) & (trend_df[col] < y_end)),
            mode='lines',
            line=dict(color=color, width=3),
            showlegend=False
        ))

    fig.update_layout(title=f"{get_chart_title('trend')} (Last {days} Days)", xaxis_title="Date", yaxis_title="Index (0-100)", template="plotly_white", yaxis_range=[0, 100])
    return fig


def plot_dealer_net_position_ranking(df: pd.DataFrame) -> Optional[go.Figure]:
    """
    繪製一個水平長條圖，顯示各類部位的最新淨值排名。
    """
    positions = {
        "Net": "dealer_net_positions",
        "Long-Term": "dealer_long_term_positions",
        "Short-Term": "dealer_short_term_positions"
    }

    latest_values = {}
    for name, col in positions.items():
        if col in df and not df[col].dropna().empty:
            latest_values[name] = df[col].dropna().iloc[-1] / 1000  # 轉換為 Billions
        else:
            latest_values[name] = 0

    if not any(p != 0 for p in latest_values.values()):
        return None

    data_series = pd.Series(latest_values).sort_values()

    fig = go.Figure(go.Bar(
        x=data_series.values,
        y=data_series.index,
        orientation='h',
        marker=dict(color='skyblue'),
        text=[f'{v:.2f}' for v in data_series.values],
        textposition='inside'
    ))

    fig.update_layout(
        title_text="Latest Net Value of Treasury Positions (in Billions USD)",
        xaxis_title="Amount (Billions USD)",
        yaxis_title="Position Type",
        template="plotly_white",
        margin=dict(l=150) # 增加左邊距以顯示長標籤
    )
    return fig

def plot_dealer_position_change_ranking(df: pd.DataFrame) -> Optional[go.Figure]:
    """
    繪製一個水平長條圖，顯示各類部位最近一週的變動排名。
    """
    positions = {
        "Net": "dealer_net_positions",
        "Long-Term": "dealer_long_term_positions",
        "Short-Term": "dealer_short_term_positions"
    }

    changes = {}
    # 修正：改為計算最新的兩個數據點之間的變動，以增加穩定性
    for name, col in positions.items():
        series = df[col].dropna()
        if len(series) >= 2:
            # 取用最新的兩個數據點
            latest_value = series.iloc[-1]
            previous_value = series.iloc[-2]

            change = (latest_value - previous_value) / 1000 # 轉換為 Billions
            changes[name] = change
        else:
            # 如果數據點少於兩個，則無法計算變動
            changes[name] = 0

    if not any(c != 0 for c in changes.values()):
        return None

    data_series = pd.Series(changes).sort_values()

    colors = ['#2ca02c' if v >= 0 else '#d62728' for v in data_series.values]

    fig = go.Figure(go.Bar(
        x=data_series.values,
        y=data_series.index,
        orientation='h',
        marker_color=colors,
        text=[f'{v:+.2f}' for v in data_series.values],
        textposition='inside'
    ))

    fig.update_layout(
        title_text="Weekly Change in Treasury Positions (in Billions USD)",
        xaxis_title="Change in Amount (Billions USD)",
        yaxis_title="Position Type",
        template="plotly_white",
        margin=dict(l=150) # 增加左邊距
    )
    return fig