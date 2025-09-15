# -*- coding: utf-8 -*-
"""
POC script for quantitative analysis.
This script fetches stock data, calculates performance metrics, and generates an HTML report with a Plotly chart.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
import plotly.graph_objects as go
import os
import warnings

# --- 設定 ---
warnings.filterwarnings("ignore", category=FutureWarning)

# 定義股票代號和分析期間
STOCK_TICKER = "TSM"  # 台積電 ADR
BENCHMARK_TICKER = "^TWII" # 台灣加權指數
END_DATE = datetime.now()
START_DATE = END_DATE - timedelta(days=3 * 365)
RISK_FREE_RATE = 0.0 # 無風險利率，為簡化計算設為 0
REPORTS_DIR = "reports"

# --- 1. 資料獲取 ---
def fetch_data(ticker, start, end):
    """使用 yfinance 下載指定期間的股價資料"""
    print(f"正在下載 {ticker} 從 {start.strftime('%Y-%m-%d')} 到 {end.strftime('%Y-%m-%d')} 的資料...")
    data = yf.download(ticker, start=start, end=end, progress=False)
    if data.empty:
        raise ValueError(f"無法下載 {ticker} 的資料，請檢查代號是否正確或網路連線。")
    print(f"成功下載 {len(data)} 筆資料。")
    # 使用 Adj Close 計算報酬，如果不存在（例如指數），則使用 Close
    price_col = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
    print(f"使用 '{price_col}' 作為 {ticker} 的價格欄位。")
    data = data[[price_col]].rename(columns={price_col: 'price'})
    return data

# --- 2. 指標計算引擎 ---
def calculate_metrics(prices, benchmark_prices):
    """計算所有需要的量化指標"""
    if not isinstance(prices, pd.DataFrame) or 'price' not in prices.columns:
        raise ValueError("輸入的 'prices' 必須是包含 'price' 欄位的 DataFrame")
    if not isinstance(benchmark_prices, pd.DataFrame) or 'price' not in benchmark_prices.columns:
        raise ValueError("輸入的 'benchmark_prices' 必須是包含 'price' 欄位的 DataFrame")

    df = pd.DataFrame(index=prices.index)
    df['price'] = prices['price']
    df['benchmark_price'] = benchmark_prices['price']
    df = df.dropna()

    # 使用 pandas.pct_change() 計算每日報酬率，更為直接可靠
    df['daily_return'] = df['price'].pct_change()
    df['benchmark_return'] = df['benchmark_price'].pct_change()
    df = df.dropna() # 丟棄第一個 NaN 值

    df['equity_curve'] = (1 + df['daily_return']).cumprod()
    df['benchmark_equity_curve'] = (1 + df['benchmark_return']).cumprod()

    total_return = df['equity_curve'].iloc[-1] - 1
    benchmark_total_return = df['benchmark_equity_curve'].iloc[-1] - 1
    excess_return = total_return - benchmark_total_return

    cumulative_max = df['equity_curve'].cummax()
    drawdown = (df['equity_curve'] / cumulative_max) - 1
    max_drawdown = drawdown.min()

    cumulative_min = df['equity_curve'].cummin()
    drawup = (df['equity_curve'] / cumulative_min) - 1
    max_drawup = drawup.max()

    volatility_daily = df['daily_return'].std()

    trading_days = len(df)
    years = trading_days / 252

    annualized_return = (1 + total_return) ** (1 / years) - 1
    annualized_volatility = volatility_daily * np.sqrt(252)

    X = df['benchmark_return'].values.reshape(-1, 1)
    y = df['daily_return'].values
    model = LinearRegression()
    model.fit(X, y)
    beta = model.coef_[0]
    daily_alpha = model.intercept_
    alpha = (1 + daily_alpha) ** 252 - 1

    # 手動計算夏普比率和索提諾比率以確保穩定性
    sharpe_ratio = (annualized_return - RISK_FREE_RATE) / (annualized_volatility + 1e-9)

    # 計算下行波動率
    downside_returns = df['daily_return'].copy()
    downside_returns[downside_returns > 0] = 0
    annualized_downside_volatility = downside_returns.std() * np.sqrt(252)
    sortino_ratio = (annualized_return - RISK_FREE_RATE) / (annualized_downside_volatility + 1e-9)

    win_rate = (df['daily_return'] > 0).sum() / trading_days

    health_score = (annualized_return * sortino_ratio) / (abs(max_drawdown) + 1e-9)

    metrics = {
        "data": df,
        "total_return": total_return,
        "benchmark_total_return": benchmark_total_return,
        "excess_return": excess_return,
        "max_drawup": max_drawup,
        "max_drawdown": max_drawdown,
        "volatility_daily": volatility_daily,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "alpha": alpha,
        "beta": beta,
        "sharpe_ratio": sharpe_ratio if isinstance(sharpe_ratio, (int, float)) else float(sharpe_ratio.iloc[-1]),
        "sortino_ratio": sortino_ratio if isinstance(sortino_ratio, (int, float)) else float(sortino_ratio.iloc[-1]),
        "win_rate": win_rate,
        "health_score": health_score
    }
    return metrics

# --- 3. 報告生成 ---
def generate_plot(df, output_path):
    """使用 Plotly 產生權益曲線圖"""
    print(f"正在生成圖表並儲存至 {output_path}...")
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['equity_curve'],
        mode='lines',
        name='策略權益曲線 (Strategy)',
        line=dict(color='royalblue', width=2)
    ))

    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['benchmark_equity_curve'],
        mode='lines',
        name=f'大盤指數 ({BENCHMARK_TICKER})',
        line=dict(color='grey', width=2, dash='dash')
    ))

    fig.update_layout(
        title_text='<b>策略權益曲線 vs. 大盤指數</b>',
        xaxis_title='日期',
        yaxis_title='累積報酬',
        legend_title_text='圖例',
        template='plotly_white',
        font=dict(family="Arial, sans-serif", size=12)
    )
    fig.write_html(output_path, include_plotlyjs='cdn')
    print("圖表生成完畢。")

def generate_html_report(metrics, plot_filename, output_path):
    """生成包含所有指標和圖表的 HTML 報告"""
    print(f"正在生成 HTML 報告並儲存至 {output_path}...")

    # 將指標格式化為字串
    f_metrics = {
        "total_return": f"{metrics['total_return']:.2%}",
        "benchmark_total_return": f"{metrics['benchmark_total_return']:.2%}",
        "excess_return": f"{metrics['excess_return']:.2%}",
        "max_drawup": f"{metrics['max_drawup']:.2%}",
        "max_drawdown": f"{metrics['max_drawdown']:.2%}",
        "volatility_daily": f"{metrics['volatility_daily']:.4f}",
        "annualized_return": f"{metrics['annualized_return']:.2%}",
        "annualized_volatility": f"{metrics['annualized_volatility']:.2%}",
        "alpha": f"{metrics['alpha']:.4f}",
        "beta": f"{metrics['beta']:.4f}",
        "sharpe_ratio": f"{metrics['sharpe_ratio']:.2f}",
        "sortino_ratio": f"{metrics['sortino_ratio']:.2f}",
        "win_rate": f"{metrics['win_rate']:.2%}",
        "health_score": f"{metrics['health_score']:.2f}"
    }

    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-Hant">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>量化分析報告</title>
        <style>
            body {{ font-family: 'Segoe UI', 'Microsoft JhengHei', sans-serif; margin: 20px; background-color: #f4f7f6; color: #333; }}
            .container {{ max-width: 1200px; margin: auto; background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            h1, h2 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            .score-box {{ background-color: #3498db; color: white; padding: 20px; text-align: center; border-radius: 8px; margin-bottom: 20px; }}
            .score-box h2 {{ border: none; }}
            .score-box .score {{ font-size: 3em; font-weight: bold; }}
            .chart-container {{ margin-bottom: 20px; }}
            iframe {{ width: 100%; height: 500px; border: none; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #ecf0f1; font-weight: bold; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            .metric-desc {{ font-size: 0.9em; color: #7f8c8d; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>量化分析報告：{STOCK_TICKER}</h1>
            <p>分析期間：{START_DATE.strftime('%Y-%m-%d')} 至 {END_DATE.strftime('%Y-%m-%d')}</p>

            <div class="score-box">
                <h2>策略健康分數 (Strategy Health Score)</h2>
                <div class="score">{f_metrics['health_score']}</div>
            </div>

            <h2>(一) 核心圖表</h2>
            <div class="chart-container">
                <iframe src="{plot_filename}"></iframe>
            </div>

            <h2>(二) 關鍵績效指標 (KPI)</h2>
            <h3>表格一：期間績效表現 (Performance Snapshot)</h3>
            <table>
                <tr><th>指標 (Metric)</th><th>數值 (Value)</th><th>說明 (Description)</th></tr>
                <tr><td>期間總報酬率</td><td>{f_metrics['total_return']}</td><td class="metric-desc">從文章日期持有至今的總報酬</td></tr>
                <tr><td>同期大盤報酬率</td><td>{f_metrics['benchmark_total_return']}</td><td class="metric-desc">同期加權指數 ({BENCHMARK_TICKER}) 的表現</td></tr>
                <tr><td>超額報酬 (Alpha)</td><td>{f_metrics['excess_return']}</td><td class="metric-desc">策略報酬率減去大盤報酬率，衡量選股能力</td></tr>
                <tr><td>期間最大漲幅</td><td>{f_metrics['max_drawup']}</td><td class="metric-desc">從期間低點到之後高點的最大漲幅</td></tr>
                <tr><td>最大回撤 (MDD)</td><td>{f_metrics['max_drawdown']}</td><td class="metric-desc">從期間高點到之後低點的最大回撤，衡量風險</td></tr>
                <tr><td>期間波動率 (日)</td><td>{f_metrics['volatility_daily']}</td><td class="metric-desc">報酬的標準差，衡量價格波動的劇烈程度</td></tr>
            </table>

            <h3>表格二：風險與報酬分析 (Risk & Return Analysis)</h3>
            <table>
                <tr><th>指標 (Metric)</th><th>數值 (Value)</th><th>說明 (Description)</th></tr>
                <tr><td>年化報酬率</td><td>{f_metrics['annualized_return']}</td><td class="metric-desc">將報酬率換算成年單位，方便比較</td></tr>
                <tr><td>年化波動率</td><td>{f_metrics['annualized_volatility']}</td><td class="metric-desc">衡量策略的年度價格波動風險</td></tr>
                <tr><td>Alpha</td><td>{f_metrics['alpha']}</td><td class="metric-desc">衡量策略相對於大盤的超額報酬，是剝離市場風險後的主動管理能力指標</td></tr>
                <tr><td>Beta (β)</td><td>{f_metrics['beta']}</td><td class="metric-desc">衡量策略與大盤的相關性及波動性。β > 1 表示比大盤更波動</td></tr>
                <tr><td>夏普比率 (Sharpe Ratio)</td><td>{f_metrics['sharpe_ratio']}</td><td class="metric-desc">衡量每承受一單位總風險，所獲得的超額報酬</td></tr>
                <tr><td>索提諾比率 (Sortino Ratio)</td><td>{f_metrics['sortino_ratio']}</td><td class="metric-desc">類似夏普比率，但只考慮下行風險（虧損）</td></tr>
                <tr><td>勝率 (Win Rate)</td><td>{f_metrics['win_rate']}</td><td class="metric-desc">所有交易中，獲利交易的比例</td></tr>
            </table>
        </div>
    </body>
    </html>
    """

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_template)
    print("HTML 報告生成完畢。")


# --- 主執行區塊 ---
if __name__ == "__main__":
    try:
        # 建立 reports 目錄
        if not os.path.exists(REPORTS_DIR):
            os.makedirs(REPORTS_DIR)

        # 1. 獲取資料
        stock_data = fetch_data(STOCK_TICKER, START_DATE, END_DATE)
        benchmark_data = fetch_data(BENCHMARK_TICKER, START_DATE, END_DATE)

        # 2. 計算指標
        print("\n正在計算策略指標...")
        results = calculate_metrics(stock_data, benchmark_data)
        print("指標計算完成。")

        # 3. 生成報告
        plot_path_relative = "poc_performance_chart.html"
        plot_path_full = os.path.join(REPORTS_DIR, plot_path_relative)
        report_path_full = os.path.join(REPORTS_DIR, "quantitative_analysis_report.html")

        generate_plot(results['data'], plot_path_full)
        generate_html_report(results, plot_path_relative, report_path_full)

        print(f"\n✅ 分析報告已成功生成於 {report_path_full}")

    except Exception as e:
        print(f"\n❌ 執行過程中發生錯誤：{e}")
