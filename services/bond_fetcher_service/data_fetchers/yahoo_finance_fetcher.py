# services/bond_data_service/data_fetchers/yahoo_finance_fetcher.py
import pandas as pd
import yfinance as yf
import logging
from datetime import datetime, timedelta

# 設置日誌
logger = logging.getLogger(__name__)

def fetch_move_index_data(api_key: str = None):
    """
    從 Yahoo Finance 抓取 MOVE 指數 (^MOVE) 的歷史數據。
    此函式不使用 api_key，保留參數是為了與其他 fetcher 保持一致。

    Returns:
        pd.Series: 一個時間序列，索引為日期，值為 MOVE 指數的收盤價。
                   如果失敗則回傳一個空的 Series。
    """
    ticker_symbol = '^MOVE'
    logger.info(f"開始從 Yahoo Finance 抓取 {ticker_symbol} 數據...")
    print(f"開始從 Yahoo Finance 抓取 {ticker_symbol} 數據...")

    # 我們抓取一個較長的時間範圍以確保數據完整性
    end_date = datetime.now()
    start_date = end_date - timedelta(days=10*365) # 抓取過去10年的數據

    try:
        move_ticker = yf.Ticker(ticker_symbol)
        # 使用 download 比 history 更穩定
        move_data = yf.download(ticker_symbol, start=start_date, end=end_date, progress=False)

        if move_data.empty or 'Close' not in move_data.columns:
            logger.warning(f"從 Yahoo Finance 抓取 {ticker_symbol} 數據失敗，回傳了空的 DataFrame 或缺少 'Close' 欄。")
            print(f"從 Yahoo Finance 抓取 {ticker_symbol} 數據失敗，回傳了空的 DataFrame 或缺少 'Close' 欄。")
            return pd.Series(dtype='float64')

        move_series = move_data['Close'].dropna()
        move_series.name = 'move_index'

        # 標準化索引
        move_series.index = pd.to_datetime(move_series.index).normalize()

        logger.info(f"成功從 Yahoo Finance 抓取並處理了 {len(move_series)} 筆 {ticker_symbol} 數據。")
        print(f"成功從 Yahoo Finance 抓取並處理了 {len(move_series)} 筆 {ticker_symbol} 數據。")
        return move_series

    except Exception as e:
        logger.error(f"從 Yahoo Finance 抓取 {ticker_symbol} 數據時發生未預期錯誤: {e}", exc_info=True)
        print(f"從 Yahoo Finance 抓取 {ticker_symbol} 數據時發生未預期錯誤: {e}")
        return pd.Series(dtype='float64')