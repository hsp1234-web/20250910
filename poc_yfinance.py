# --- 檔案: poc_yfinance.py ---
# --- 說明: 用於驗證 StockSuffixHelper 和 yfinance 整合的 PoC 腳本 ---

import yfinance as yf
import sys
from pathlib import Path
import logging

# --- 路徑設定，確保能從 src 匯入 ---
# 取得目前檔案的絕對路徑 -> .../file.py
current_file_path = Path(__file__).resolve()
# 取得專案根目錄 (假設 poc_yfinance.py 在根目錄) -> .../
project_root = current_file_path.parent
# 取得 src 目錄路徑 -> .../src
src_path = project_root / "src"
# 將 src 目錄加入 Python 的搜尋路徑
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# --- 匯入我們的輔助工具 ---
try:
    from tools.taiwan_stock_suffix_helper import SUFFIX_HELPER
except ImportError as e:
    print(f"無法匯入 SUFFIX_HELPER: {e}")
    print("請確認 `src/tools/taiwan_stock_suffix_helper.py` 檔案存在且路徑設定正確。")
    sys.exit(1)

# 設定日誌，以便觀察 SUFFIX_HELPER 的內部活動
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 測試代號列表 ---
# 包含上市、上櫃、錯誤格式、以及非台灣股票
symbols_to_test = [
    '2330',       # 台積電 (上市)
    '00969B',     # 元大零息超長美債 (上櫃，此為原始問題代號)
    '00969b.tw',  # AI 可能產生的錯誤格式
    '6488',       # 環球晶 (上櫃)
    '2317.TW',    # 鴻海 (上市，已是正確格式)
    '8069.TWO',   # 元太 (上櫃，已是正確格式)
    'TSM',        # 美股代號 (應保持不變)
    'GOOG',       # 美股代號 (應保持不變)
    'INVALID',    # 一個無效的代號
    ' 2330 ',     # 帶有空白的代號
]

print("="*50)
print("=== 開始測試台灣股票代號校正與 yfinance 整合 ===")
print("="*50 + "\n")

# 檢查輔助工具是否成功初始化
if not SUFFIX_HELPER._initialized:
    print("\n❌ StockSuffixHelper 初始化失敗，測試無法繼續。")
    print("請檢查 twstock 的網路連線或資料來源。\n")
    sys.exit(1)

# --- 執行測試 ---
for original_symbol in symbols_to_test:
    print(f"--- 測試原始代號: '{original_symbol}' ---")

    # 1. 使用我們的輔助工具校正代號
    corrected_symbol = SUFFIX_HELPER.get_corrected_symbol(original_symbol)
    print(f"校正後代號: '{corrected_symbol}'")

    # 2. 使用校正後的代號與 yfinance 互動
    try:
        ticker_obj = yf.Ticker(corrected_symbol)
        history = ticker_obj.history(period="5d")

        if not history.empty:
            print(f"✅ yfinance 驗證成功: 使用 '{corrected_symbol}' 已成功下載資料。")
        else:
            # 檢查是否為本來就預期會失敗的無效代號
            if original_symbol.upper() == 'INVALID':
                print(f"✅ yfinance 驗證成功: 正確地無法為無效代號 '{corrected_symbol}' 找到資料。")
            else:
                print(f"❌ yfinance 驗證失敗: 使用 '{corrected_symbol}' 無法下載資料。")

    except Exception as e:
        print(f"❌ yfinance 驗證錯誤: 測試 '{corrected_symbol}' 時發生例外: {e}")

    print("-" * 40 + "\n")

print("="*50)
print("=== 所有測試已完成 ===")
print("="*50)
