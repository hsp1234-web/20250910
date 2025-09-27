# services/bond_data_service/data_fetchers/fred_sofr_fetcher.py
import pandas as pd
from openbb import obb
import logging

# 設置日誌
logger = logging.getLogger(__name__)

def fetch_sofr_data(api_key: str):
    """
    使用 OpenBB SDK 獲取擔保隔夜融資利率 (SOFR) 的時間序列資料。

    Args:
        api_key (str): FRED API 金鑰 (注意：OpenBB SDK 會自動從環境變數或設定檔中讀取，此參數主要為相容性保留)。

    Returns:
        pd.Series: 包含 SOFR 資料的 pandas Series，索引為日期。
                   如果發生錯誤或找不到資料，則返回一個空的 Series。
    """
    try:
        # OpenBB 的憑證會自動管理，此處的 api_key 參數是為了保持介面兼容
        # 實際的金鑰應設定在環境變數 OBB_FRED_API_KEY 中
        results = obb.fixedincome.sofr()

        # 修正：OpenBB 的 results.results 是一個列表，應直接檢查其是否為空
        if not results or not results.results:
            logger.warning("從 OpenBB 未獲取到 SOFR 數據。")
            print("警告：從 OpenBB 未獲取到 SOFR 數據。")
            return pd.Series(dtype='float64', name='sofr')

        # 將 OpenBB 的結果物件轉換為 pandas DataFrame
        df = results.to_df()

        # 假設 'rate' 是包含利率值的欄位，這是 OpenBB 的標準輸出
        # 我們也需要確保回傳的 Series 名稱是 'sofr' 以保持與舊函式的兼容性
        series = df['rate'].rename('sofr')

        # 數據清理
        series = series.dropna()

        # OpenBB 回傳的索引通常已經是標準化的 datetime，但為保險起見仍進行一次標準化
        series.index = pd.to_datetime(series.index).normalize()

        logger.info(f"成功從 OpenBB 獲取到 {len(series)} 筆 SOFR 數據。")
        print(f"成功從 OpenBB 獲取到 {len(series)} 筆 SOFR 數據。")
        return series

    except Exception as e:
        logger.error(f"從 OpenBB 獲取 SOFR 數據時發生錯誤: {e}", exc_info=True)
        print(f"錯誤：從 OpenBB 獲取 SOFR 數據時發生錯誤: {e}")
        return pd.Series(dtype='float64', name='sofr')