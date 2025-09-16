# --- 檔案: final_verification.py ---
# --- 說明: 最終整合驗證腳本 ---

import sys
from pathlib import Path
import logging

# --- 路徑設定，確保能從 src 匯入 ---
current_file_path = Path(__file__).resolve()
project_root = current_file_path.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# --- 匯入正式模組 ---
try:
    from tools.taiwan_stock_suffix_helper import SUFFIX_HELPER
    from tools.quantitative_analyzer import find_valid_yfinance_symbol
except ImportError as e:
    print(f"無法匯入正式模組: {e}")
    print("請確認 `src/tools/` 下的檔案都存在。")
    sys.exit(1)

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 綜合測試案例 ---
symbols_to_test = [
    # 台灣案例
    '2330',       # 台積電 (上市)
    '00969B',     # 元大零息超長美債 (上櫃)
    '00969b.tw',  # 錯誤格式的 ETF
    '6488.TWO',   # 環球晶 (上櫃，已正確)
    # 國際案例
    'GOOG',       # 美國股票
    'ADS',        # Adidas (德國)
    '0700',       # 騰訊 (香港)
    'VOD.L',      # Vodafone (倫敦，已正確)
    # 無效案例
    'NOTASYMBOL',
    '1234.XX',    # 無效後綴
]

if __name__ == '__main__':
    print("="*60)
    print("=== 開始最終整合驗證 ===")
    print("模擬 API 路由中的兩階段校正流程")
    print("="*60 + "\n")

    if not SUFFIX_HELPER._initialized:
        print("\n❌ StockSuffixHelper 初始化失敗，測試無法繼續。\n")
        sys.exit(1)

    for symbol in symbols_to_test:
        print(f"--- 原始輸入: '{symbol}' ---")

        # 階段 1: 台灣專用校正
        corrected_for_tw = SUFFIX_HELPER.get_corrected_symbol(symbol)
        print(f"台灣校正後: '{corrected_for_tw}'")

        # 階段 2: 全域驗證與重試
        final_symbol = find_valid_yfinance_symbol(corrected_for_tw)
        print(f"全域校正後: '{final_symbol}'")

        if final_symbol:
            print(f"✅ 最終結果: 找到的有效代號為 -> {final_symbol}\n")
        else:
            print(f"❌ 最終結果: 未能為 '{symbol}' 找到任何有效代號。\n")

    print("="*60)
    print("=== 最終整合驗證完成 ===")
    print("="*60)
