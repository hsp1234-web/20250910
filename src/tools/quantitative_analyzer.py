import yfinance as yf
import pandas as pd
import numpy as np
import logging
from datetime import datetime

log = logging.getLogger(__name__)

def to_float(value: any) -> float | None:
    """
    Safely convert a value that should be a scalar into a standard Python float.
    Handles None, numpy numbers, single-item pandas Series, NaN, and infinity.
    If a Series is passed, it takes the first element.
    """
    if value is None:
        return None
    # If it's a pandas Series/DataFrame, take the first element.
    if isinstance(value, (pd.Series, pd.DataFrame)):
        if value.empty:
            return None
        value = value.iloc[0]
    # Check for NaN or infinity
    if isinstance(value, (int, float, np.number)) and (np.isnan(value) or np.isinf(value)):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def calculate_performance_stats(symbol: str, start_date: str, end_date: str = None) -> dict:
    """
    計算給定股票代號在指定期間內的績效指標。
    """
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')

    log.info(f"開始為代號 {symbol} 計算從 {start_date} 到 {end_date} 的績效...")

    try:
        stock_data = yf.download(symbol, start=start_date, end=end_date, progress=False)
        benchmark_data = yf.download('^TWII', start=start_date, end=end_date, progress=False)

        if stock_data.empty:
            log.error(f"找不到代號 {symbol} 在指定期間的股價資料。")
            return {"error": f"找不到代號 {symbol} 的股價資料。"}
        if benchmark_data.empty:
            log.warning("找不到大盤 (^TWII) 的資料，部分指標 (Alpha, Beta) 將無法計算。")

        stock_price_col = 'Adj Close' if 'Adj Close' in stock_data.columns else 'Close'
        benchmark_price_col = 'Adj Close' if 'Adj Close' in benchmark_data.columns else 'Close'

        stock_data['daily_return'] = stock_data[stock_price_col].pct_change()
        if not benchmark_data.empty:
            benchmark_data['daily_return'] = benchmark_data[benchmark_price_col].pct_change()

        stock_returns = stock_data['daily_return'].dropna()
        benchmark_returns = benchmark_data['daily_return'].dropna() if not benchmark_data.empty else pd.Series(dtype=np.float64)

        if len(stock_returns) < 2:
             return {"error": "股價數據不足，無法計算績效。"}

        total_return = (stock_data[stock_price_col].iloc[-1] / stock_data[stock_price_col].iloc[0]) - 1
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

        final_stats = {
            "total_return": to_float(total_return),
            "annualized_return": to_float(annualized_return),
            "annualized_volatility": to_float(annualized_volatility),
            "max_drawdown": to_float(max_drawdown),
            "sharpe_ratio": to_float(sharpe_ratio),
            "alpha": to_float(alpha),
            "beta": to_float(beta)
        }
        return final_stats

    except Exception as e:
        log.error(f"為代號 {symbol} 計算績效時發生錯誤: {e}", exc_info=True)
        return {"error": f"計算績效時發生錯誤: {e}"}

if __name__ == '__main__':
    test_symbol = '2330.TW'
    test_start_date = '2023-01-01'
    stats = calculate_performance_stats(test_symbol, test_start_date)

    if "error" in stats:
        print(f"計算失敗: {stats['error']}")
    else:
        print(f"--- {test_symbol} 從 {test_start_date} 以來的績效 ---")
        for key, value in stats.items():
            if value is not None:
                print(f"{key.replace('_', ' ').title():<25}: {value:.4f}")
            else:
                print(f"{key.replace('_', ' ').title():<25}: N/A")
