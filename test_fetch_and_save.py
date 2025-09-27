import logging
import sys
from pathlib import Path

# 設定日誌，以便在控制台中看到輸出
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 將 'services' 目錄添加到 Python 路徑中，以便可以導入我們的模組
# 專案根目錄是 /app
project_root = Path(__file__).parent
services_path = project_root / 'services'
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

def run_test():
    """
    導入並執行 fetch_hys_data 函式來測試數據抓取和儲存。
    """
    try:
        # 從 services.bond_data_service.data_fetchers 導入 fred_hys_fetcher 模組
        from services.bond_data_service.data_fetchers import fred_hys_fetcher

        logger.info("開始測試 fetch_hys_data 函式...")

        # 執行函式
        result_series = fred_hys_fetcher.fetch_hys_data()

        if not result_series.empty:
            logger.info("測試成功：fetch_hys_data 函式已執行並返回了數據。")
            logger.info(f"返回的 Series 包含 {len(result_series)} 筆數據。")
            logger.info("請檢查日誌輸出以確認資料庫儲存操作。")
        else:
            logger.error("測試失敗：fetch_hys_data 函式返回了空的 Series。")

    except ImportError as e:
        logger.critical(f"導入模組時發生錯誤，請檢查 sys.path 和檔案結構: {e}", exc_info=True)
    except Exception as e:
        logger.critical(f"執行測試時發生未預期的錯誤: {e}", exc_info=True)

if __name__ == '__main__':
    run_test()