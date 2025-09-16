# --- 檔案: poc_international_finder.py ---
# --- 說明: 一個獨立的 PoC 腳本，用於驗證國際股票代號的後綴猜測與校正邏輯 ---

import yfinance as yf
import logging

# --- 設定 ---
# 設定日誌，以便觀察函式的內部活動
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定義我們想要猜測的後綴列表
YFINANCE_SUFFIXES = [
    '.L',   # London Stock Exchange
    '.F',   # Frankfurt Stock Exchange
    '.HK',  # Hong Kong Stock Exchange
    '.DE',  # XETRA (Germany)
    '.PA',  # Euronext Paris
    '.AS',  # Euronext Amsterdam
    '.TO',  # Toronto Stock Exchange (Canada)
    '.AX',  # Australian Securities Exchange
    # 可以根據需求繼續添加
]

# --- 核心函式 (原型) ---

def _check_symbol_validity(symbol: str) -> bool:
    """
    一個精簡的輔助函式，僅用於檢查單一 yfinance 代號是否能獲取資料。
    在 PoC 中，我們簡化了錯誤處理。
    """
    if not symbol:
        return False
    try:
        ticker = yf.Ticker(symbol)
        # 檢查是否有歷史資料是比檢查 .info 更可靠的方法
        history = ticker.history(period="5d")
        if history.empty:
            logging.info(f"檢查 '{symbol}': 失敗 (找不到歷史資料)。")
            return False
        logging.info(f"檢查 '{symbol}': 成功。")
        return True
    except Exception as e:
        logging.error(f"檢查 '{symbol}' 時發生例外: {e}")
        return False

def find_valid_yfinance_symbol_poc(symbol: str) -> str | None:
    """
    此函式為 `find_valid_yfinance_symbol` 的 PoC 原型。
    它會嘗試找到一個有效的 yfinance 代號。
    1. 檢查原始代號。
    2. 如果失敗，則嘗試附加後綴列表中的後綴進行重試。
    回傳有效的完整代號字串，或在失敗時回傳 None。
    """
    if not symbol or not isinstance(symbol, str):
        return None

    symbol = symbol.strip().upper() # 標準化輸入

    # 1. 嘗試原始代號 (適用於美國市場或已格式化的代號)
    logging.info(f"步驟 1: 嘗試原始代號 '{symbol}'...")
    if _check_symbol_validity(symbol):
        return symbol

    # 2. 如果失敗，且代號不包含 '.' (避免對 'VOD.L' 這樣的代號再次添加後綴)
    if '.' in symbol:
        logging.warning(f"代號 '{symbol}' 包含 '.' 且驗證失敗，將不進行後綴重試。")
        return None

    # 3. 啟動後綴重試邏輯
    logging.info(f"步驟 2: 為 '{symbol}' 啟動後綴重試邏輯...")
    for suffix in YFINANCE_SUFFIXES:
        test_symbol = f"{symbol}{suffix}"
        logging.info(f"重試: 正在嘗試 '{test_symbol}'...")
        if _check_symbol_validity(test_symbol):
            logging.info(f"成功找到有效代號: '{test_symbol}'")
            return test_symbol

    logging.warning(f"'{symbol}' 在嘗試所有後綴後，仍找不到有效的 yfinance 代號。")
    return None

# --- 測試案例 ---
if __name__ == '__main__':
    # 準備一組需要測試的代號
    symbols_to_test = [
        'GOOG',       # 美國股票 (應直接成功)
        'ADS',        # Adidas (德國，應找到 ADS.F 或 ADS.DE)
        '0700',       # 騰訊 (香港，應找到 0700.HK)
        'VOD.L',      # Vodafone (倫敦，已正確格式化)
        'NOTASYMBOL', # 一個無效的代號
        'BARC',       # Barclays (倫敦, 應找到 BARC.L)
    ]

    print("="*60)
    print("=== 開始 PoC：測試國際股票代號的後綴猜測機制 ===")
    print("="*60 + "\n")

    for symbol in symbols_to_test:
        print(f"--- 正在處理原始輸入: '{symbol}' ---")
        valid_symbol = find_valid_yfinance_symbol_poc(symbol)
        if valid_symbol:
            print(f"✅ 最終結果: 找到的有效代號為 -> {valid_symbol}\n")
        else:
            print(f"❌ 最終結果: 未能為 '{symbol}' 找到任何有效代號。\n")

    print("="*60)
    print("=== PoC 測試完成 ===")
    print("="*60)
