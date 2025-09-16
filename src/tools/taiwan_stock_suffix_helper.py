# --- 檔案: src/tools/taiwan_stock_suffix_helper.py ---
# --- 說明: 一個輔助模組，用於校正台灣股票代號的 yfinance 後綴 (.TW 或 .TWO)。---

import logging
import twstock
import re
from threading import Lock

log = logging.getLogger(__name__)

def _update_twstock_codes():
    """
    一個獨立的頂層函式，用於呼叫 twstock 的 dunder 更新方法。
    這可以避免在類別內部呼叫時觸發 Python 的名稱修飾 (name mangling)。
    """
    try:
        # 直接呼叫 twstock 的 '私有' 更新函式
        twstock.__update_codes()
    except Exception as e:
        # 捕捉並記錄任何在更新過程中發生的錯誤
        log.error(f"twstock.__update_codes() 執行時發生錯誤: {e}", exc_info=True)
        # 即使失敗也要拋出例外，讓呼叫者知道
        raise

class StockSuffixHelper:
    """
    一個輔助類別，用於判斷台灣股票代號應使用 .TW (上市) 還是 .TWO (上櫃)。
    它會從 `twstock` 獲取並快取股票列表以提高效能。
    採用單例模式確保在應用程式生命週期中只初始化一次。
    """
    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                # 再次檢查，防止多執行緒同時通過第一個檢查
                if not cls._instance:
                    cls._instance = super(StockSuffixHelper, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # 防止重複初始化
        if hasattr(self, '_initialized') and self._initialized:
            return
        with self._lock:
            if hasattr(self, '_initialized') and self._initialized:
                return

            self.twse_codes = set()
            self.tpex_codes = set()
            self._initialized = False
            # JULES-FIX: 移除在 __init__ 時的自動更新，改為延遲載入
            log.info("StockSuffixHelper 已建立但尚未初始化資料。將在首次使用時載入。")


    def _update_and_load_codes(self):
        """
        從 twstock 更新並載入上市(TWSE)和上櫃(TPEx)的股票代號。
        """
        log.info("正在初始化 StockSuffixHelper，準備更新台灣股票代號列表...")
        try:
            # JULES-FIX (2): 呼叫我們自己的頂層函式來避免名稱修飾
            _update_twstock_codes()

            # twstock.codes 是一個字典，key 是股票代號，value 是 twstock.StockAttribute 物件
            # 我們需要檢查 StockAttribute 物件的 'type' 屬性
            for code, attr in twstock.codes.items():
                # JULES-FIX: 移除 attr.type == '股票' 的過濾條件
                # 這樣才能包含 ETF、受益憑證等非股票類型的交易商品
                if hasattr(attr, 'market'):
                    if attr.market == '上市':
                        self.twse_codes.add(code)
                    elif attr.market == '上櫃':
                        self.tpex_codes.add(code)

            if not self.twse_codes and not self.tpex_codes:
                 log.warning("twstock 代號列表更新後，上市或上櫃列表仍為空。請檢查 twstock 的資料來源。")
            else:
                log.info(f"股票代號列表載入成功。上市: {len(self.twse_codes)} 支, 上櫃: {len(self.tpex_codes)} 支。")
                self._initialized = True

        except Exception as e:
            log.error(f"從 twstock 更新股票代號列表時發生錯誤: {e}", exc_info=True)
            # 即使更新失敗，也將 initialized 設為 True，避免不斷重試
            self._initialized = True


    def get_corrected_symbol(self, symbol: str) -> str:
        """
        接收一個可能是 AI 提取的股票代號，回傳其正確的 yfinance 格式。
        - 如果是已知的台灣上市/上櫃股票，回傳 '代號.TW' 或 '代號.TWO'。
        - 如果不是，則回傳原始代號。
        """
        # JULES-FIX: 延遲載入邏輯
        # 檢查是否已初始化，如果沒有，則使用鎖來確保只有一個執行緒進行初始化
        if not self._initialized:
            with self._lock:
                # 再次檢查，因為可能有其他執行緒在等待鎖時，第一個執行緒已經完成了初始化
                if not self._initialized:
                    self._update_and_load_codes()

        if not symbol or not isinstance(symbol, str):
            return symbol

        # 移除任何已存在的 .TW 或 .TWO 後綴 (不區分大小寫)
        # 也順便移除潛在的空白字元
        clean_symbol = re.sub(r'\.(TW|TWO)$', '', symbol.strip(), flags=re.IGNORECASE)

        # JULES-FIX: 將清理後的代號轉為大寫，以進行不區分大小寫的比對
        lookup_symbol = clean_symbol.upper()

        # 檢查是否為台灣股票
        if lookup_symbol in self.twse_codes:
            corrected = f"{lookup_symbol}.TW"
            log.info(f"代號 '{symbol}' 被校正為上市股票: '{corrected}'")
            return corrected

        if lookup_symbol in self.tpex_codes:
            corrected = f"{lookup_symbol}.TWO"
            log.info(f"代號 '{symbol}' 被校正為上櫃股票: '{corrected}'")
            return corrected

        # 如果在我們的列表中找不到，可能是一個非台股代號 (如 'TSM') 或是一個無效代號
        # 在這種情況下，我們回傳原始的 symbol，讓後續的 is_ticker_valid 函式做最後的判斷
        log.info(f"代號 '{symbol}' 在台灣上市/上櫃列表中未找到，將使用原始代號進行驗證。")
        return symbol

# --- 建立單例物件供外部匯入使用 ---
SUFFIX_HELPER = StockSuffixHelper()

if __name__ == '__main__':
    # 簡易測試
    logging.basicConfig(level=logging.INFO)

    print("\n--- 測試範例 ---")
    helper = SUFFIX_HELPER

    # 確保 helper 已經初始化
    if helper._initialized:
        test_symbols = [
            '2330',       # 台積電 (上市)
            '00969B',     # 元大零息超長美債 (上櫃)
            '00969b.tw',  # 錯誤的格式
            '6488',       # 環球晶 (上櫃)
            '2317.TW',    # 鴻海 (上市，已正確)
            '8069.TWO',   # 元太 (上櫃，已正確)
            'TSM',        # 美股代號
            'INVALID',    # 無效代號
            ' 2330 ',     # 帶有空白
        ]

        for s in test_symbols:
            print(f"原始: '{s}' -> 校正後: '{helper.get_corrected_symbol(s)}'")
    else:
        print("StockSuffixHelper 初始化失敗，無法執行測試。")
