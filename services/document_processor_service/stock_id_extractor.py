import re
import twstock
import logging
from functools import lru_cache

# --- 日誌設定 ---
# 註：此處的日誌記錄器將繼承其被匯入處的設定
log = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_all_stock_codes():
    """
    獲取所有台灣股票的代號列表。
    使用 @lru_cache 來確保 `twstock.codes` 只被載入一次，並在服務生命週期內快取。
    """
    log.info("正在首次載入與快取台股股票代號列表...")
    # twstock.codes 是一個字典，我們只需要它的鍵 (股票代號)
    # 將其轉換為 set 以獲得 O(1) 的查詢效率
    return set(twstock.codes.keys())

def extract_stock_ids(text: str) -> list[str]:
    """
    從一段給定的文字中，提取所有有效的台股股票代號。

    Args:
        text: 要分析的來源文字。

    Returns:
        一個經過排序且不重複的、已驗證的有效股票代號列表。
    """
    log.info("開始從文字中提取股票代號...")

    # 步驟 1: 從快取或首次載入中，獲取所有有效的股票代號集合
    all_codes = get_all_stock_codes()

    # 步驟 2: 使用正規表示式，找出所有格式為「四位數字」的獨立單詞
    # \b 表示單字邊界，確保我們不會匹配到一個較長數字的一部分 (例如 "12345" 中的 "1234")
    potential_ids = re.findall(r'\b(\d{4})\b', text)

    if not potential_ids:
        log.info("在文字中沒有找到任何符合格式 (四位數字) 的潛在代號。")
        return []

    log.info(f"找到 {len(potential_ids)} 個潛在代號: {potential_ids}")

    # 步驟 3: 驗證每個潛在代號是否真的存在於台股代號列表中
    # 使用 set 來自動處理重複的代號，以提升效率
    valid_ids = {
        stock_id for stock_id in potential_ids if stock_id in all_codes
    }

    if not valid_ids:
        log.info("所有潛在代號都未通過驗證，沒有找到有效的股票代號。")
        return []

    # 步驟 4: 將結果轉換為排序後的列表並回傳
    result_list = sorted(list(valid_ids))
    log.info(f"提取完成，共找到 {len(result_list)} 個有效的股票代號: {result_list}")

    return result_list