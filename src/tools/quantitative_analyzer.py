import yfinance as yf
import pandas as pd
import numpy as np
import logging
from datetime import datetime
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import io
import base64

log = logging.getLogger(__name__)

def is_ticker_valid(symbol: str) -> bool:
    """
    使用 yfinance 檢查一個股票代號是否有效且可獲取資料。
    一個"有效"的代號是 Ticker 物件有 `info` 且 `info` 內有價格資訊。
    """
    if not symbol or not isinstance(symbol, str):
        return False
    try:
        log.info(f"正在驗證代號: {symbol}")
        ticker = yf.Ticker(symbol)
        # 檢查 .info 字典是否為空或缺少關鍵價格鍵
        if not ticker.info or ticker.info.get('regularMarketPrice') is None:
            # 作為後備，快速檢查是否有任何歷史資料
            history = ticker.history(period="7d")
            if history.empty:
                log.warning(f"代號 '{symbol}' 的 .info 和歷史資料均為空。標記為無效。")
                return False
        log.info(f"代號 '{symbol}' 驗證成功。")
        return True
    except Exception as e:
        # 捕獲可能發生的任何網路或 API 錯誤
        log.error(f"驗證代號 '{symbol}' 時發生例外: {e}")
        return False

def to_float(value: any) -> float | None:
    """
    Safely convert a value that should be a scalar into a standard Python float.
    Handles None, numpy numbers, single-item pandas Series, NaN, and infinity.
    If a Series is passed, it takes the first element.
    """
    if value is None:
        return None
    if isinstance(value, (pd.Series, pd.DataFrame)):
        if value.empty:
            return None
        value = value.iloc[0]
    if isinstance(value, (int, float, np.number)) and (np.isnan(value) or np.isinf(value)):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def _generate_performance_chart_html(stock_df: pd.DataFrame, benchmark_df: pd.DataFrame) -> str:
    """
    【JULES修改】使用 Matplotlib 產生權益曲線圖的 HTML 字串。
    """
    log.info("正在使用 Matplotlib 生成績效圖表...")
    try:
        # --- 字體設定 ---
        font_path = '/tmp/fonts/NotoSansTC-Regular.otf'
        import os
        if not os.path.exists(font_path):
            log.error(f"字體文件不存在於: {font_path}")
            return "<p>錯誤: 關鍵字體文件缺失，無法生成圖表。</p>"

        font_properties = fm.FontProperties(fname=font_path, size=12)
        title_font_properties = fm.FontProperties(fname=font_path, size=16)

        # --- 圖表繪製 ---
        fig, ax = plt.subplots(figsize=(10, 5)) # 調整尺寸以更好地配合頁面

        # 繪製策略權益曲線
        ax.plot(
            stock_df.index,
            (1 + stock_df['daily_return']).cumprod(),
            color='royalblue',
            linewidth=2,
            label='策略權益曲線'
        )

        # 繪製大盤指數權益曲線
        if not benchmark_df.empty:
            ax.plot(
                benchmark_df.index,
                (1 + benchmark_df['daily_return']).cumprod(),
                color='grey',
                linewidth=2,
                linestyle='--',
                label='大盤指數 (^TWII)'
            )

        # --- 圖表美化與標籤設定 ---
        ax.set_title('策略權益曲線 vs. 大盤指數', fontproperties=title_font_properties)
        ax.set_xlabel('日期', fontproperties=font_properties)
        ax.set_ylabel('累積報酬', fontproperties=font_properties)

        # 設定圖例
        legend = ax.legend(prop=font_properties)

        # 設定坐標軸刻度的字體
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontproperties(font_properties)

        ax.grid(True, linestyle='--', alpha=0.6)
        fig.autofmt_xdate() # 自動旋轉日期標籤

        # --- 轉換為 Base64 HTML ---
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig)

        chart_html = f'<img src="data:image/png;base64,{img_base64}" alt="策略績效分析圖表" style="max-width: 100%; height: auto;" />'
        log.info("Matplotlib 圖表生成並編碼成功。")

        return chart_html

    except Exception as e:
        log.error(f"使用 Matplotlib 生成圖表時發生錯誤: {e}", exc_info=True)
        return f"<p>生成圖表時發生預期外的錯誤: {e}</p>"

def calculate_performance_stats(symbol: str, start_date: str, end_date: str = None, timeout: int = 30) -> dict:
    """
    計算給定股票代號在指定期間內的績效指標，並生成圖表。
    【新增】支援網路請求超時設定。
    """
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')

    log.info(f"開始為代號 {symbol} 計算從 {start_date} 到 {end_date} 的績效 (超時: {timeout}秒)...")

    try:
        # --- 資料下載 ---
        try:
            # JULES (2025-09-15): 新增 timeout 參數
            stock_data = yf.download(symbol, start=start_date, end=end_date, progress=False, timeout=timeout)
            if stock_data.empty:
                # yfinance might not raise an exception for invalid tickers, just return an empty df.
                raise ValueError(f"下載的資料為空，代號 '{symbol}' 可能無效或在該期間無資料。")
        except Exception as e:
            log.error(f"下載代號 {symbol} 的資料時失敗: {e}")
            # 檢查是否為超時錯誤
            if "timeout" in str(e).lower():
                 return {"error": f"下載代號 '{symbol}' 的股價資料時發生超時。請嘗試增加 API 超時秒數或檢查網路連線。"}
            return {"error": f"無法下載代號 '{symbol}' 的股價資料。該代號可能已下市、不存在或在此期間無交易資料。"}

        # JULES (2025-09-15): 新增 timeout 參數
        benchmark_data = yf.download('^TWII', start=start_date, end=end_date, progress=False, timeout=timeout)
        if benchmark_data.empty:
            log.warning("找不到大盤 (^TWII) 的資料，部分指標 (Alpha, Beta) 將無法計算。")

        price_col = 'Adj Close' if 'Adj Close' in stock_data.columns else 'Close'
        benchmark_price_col = 'Adj Close' if 'Adj Close' in benchmark_data.columns else 'Close'

        stock_data['daily_return'] = stock_data[price_col].pct_change()
        if not benchmark_data.empty:
            benchmark_data['daily_return'] = benchmark_data[benchmark_price_col].pct_change()

        stock_returns = stock_data['daily_return'].dropna()
        benchmark_returns = benchmark_data['daily_return'].dropna() if not benchmark_data.empty else pd.Series(dtype=np.float64)

        if len(stock_returns) < 2:
             return {"error": "股價數據不足，無法計算績效。"}

        # --- 指標計算 ---
        total_return = (stock_data[price_col].iloc[-1] / stock_data[price_col].iloc[0]) - 1
        days = (stock_data.index[-1] - stock_data.index[0]).days
        annualized_return = (1 + total_return) ** (365.25 / days) - 1 if days > 0 else 0
        annualized_volatility = stock_returns.std() * np.sqrt(252)

        cumulative_returns = (1 + stock_returns).cumprod()
        peak = cumulative_returns.expanding(min_periods=1).max()
        drawdown = (cumulative_returns / peak) - 1
        max_drawdown = drawdown.min()

        sharpe_ratio = annualized_return / annualized_volatility if annualized_volatility != 0 else 0

        alpha, beta = None, None
        if not benchmark_returns.empty and len(benchmark_returns) > 1:
            common_returns = pd.DataFrame({'stock': stock_returns, 'benchmark': benchmark_returns}).dropna()
            if len(common_returns) > 1:
                covariance_matrix = common_returns.cov()
                covariance = covariance_matrix.iloc[0, 1]
                benchmark_variance = common_returns['benchmark'].var()
                beta = covariance / benchmark_variance if benchmark_variance != 0 else 0

                benchmark_total_return = (benchmark_data[benchmark_price_col].iloc[-1] / benchmark_data[benchmark_price_col].iloc[0]) - 1
                benchmark_annualized_return = (1 + benchmark_total_return) ** (365.25 / days) - 1 if days > 0 else 0
                alpha = annualized_return - (beta * benchmark_annualized_return)

        log.info(f"代號 {symbol} 的績效計算完成。")

        # --- 圖表生成 ---
        chart_html = _generate_performance_chart_html(stock_data, benchmark_data)

        # --- 彙整結果 ---
        final_results = {
            "stats": {
                "total_return": to_float(total_return),
                "annualized_return": to_float(annualized_return),
                "annualized_volatility": to_float(annualized_volatility),
                "max_drawdown": to_float(max_drawdown),
                "sharpe_ratio": to_float(sharpe_ratio),
                "alpha": to_float(alpha),
                "beta": to_float(beta)
            },
            "chart_html": chart_html
        }
        return final_results

    except Exception as e:
        log.error(f"為代號 {symbol} 計算績效時發生錯誤: {e}", exc_info=True)
        return {"error": f"計算績效時發生錯誤: {e}"}

if __name__ == '__main__':
    test_symbol = '2330.TW'
    test_start_date = '2023-01-01'
    results = calculate_performance_stats(test_symbol, test_start_date)

    if "error" in results:
        print(f"計算失敗: {results['error']}")
    else:
        print(f"--- {test_symbol} 從 {test_start_date} 以來的績效 ---")
        for key, value in results['stats'].items():
            if value is not None:
                print(f"{key.replace('_', ' ').title():<25}: {value:.4f}")
            else:
                print(f"{key.replace('_', ' ').title():<25}: N/A")

        # 為了測試，將圖表HTML寫入檔案
        with open("temp_chart.html", "w", encoding="utf-8") as f:
            f.write(results['chart_html'])
        print("\n圖表已暫存至 temp_chart.html")
