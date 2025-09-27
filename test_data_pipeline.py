# test_data_pipeline.py

import logging
import time
import sqlite3
from pathlib import Path
import os
import sys

# --- 路徑設定，確保可以導入 services 中的模組 ---
# 專案根目錄是 /app
project_root = Path(__file__).parent
services_path = project_root / 'services'
sys.path.insert(0, str(project_root))

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- 導入我們需要測試的模組 ---
from services.bond_data_service.data_manager import DataManager
from services.bond_data_service.stress_index_calculator import calculate_full_metrics

# --- 測試用的常數 ---
DB_FILE = project_root / 'financial_data.sqlite'
# 從環境變數讀取 API Key，如果沒有則使用一個預設的假 Key
FRED_API_KEY = os.getenv("FRED_API_KEY", "YOUR_API_KEY_HERE")
START_DATE = "2018-01-01"
END_DATE = "2025-09-27"

def clear_database():
    """清空 time_series_data 表以進行乾淨的測試。"""
    if not DB_FILE.exists():
        logger.warning(f"資料庫檔案 {DB_FILE} 不存在，無需清空。")
        return
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        logger.info("正在清空 'time_series_data' 資料表...")
        cursor.execute("DELETE FROM time_series_data")
        conn.commit()
        logger.info("資料表已清空。")
    except sqlite3.Error as e:
        logger.error(f"清空資料庫時發生錯誤: {e}")
    finally:
        if conn:
            conn.close()

def check_db_content():
    """檢查資料庫中是否已存入數據。"""
    if not DB_FILE.exists():
        logger.error("檢查失敗：資料庫檔案不存在。")
        return 0
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT ticker) FROM time_series_data")
        ticker_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM time_series_data")
        row_count = cursor.fetchone()[0]
        logger.info(f"資料庫中包含 {ticker_count} 個獨立的 Ticker 和總共 {row_count} 筆數據。")
        return row_count
    except sqlite3.Error as e:
        logger.error(f"檢查資料庫內容時發生錯誤: {e}")
        return 0
    finally:
        if conn:
            conn.close()

def run_pipeline_test():
    """執行完整的數據管道整合測試。"""
    logger.info("====== 開始數據管道整合測試 ======")

    # 0. 初始化 DataManager
    data_manager = DataManager(api_key=FRED_API_KEY)

    # 1. 清空資料庫，模擬首次執行
    clear_database()
    logger.info("\n--- 第一次執行 (預期從網路抓取) ---")
    start_time_first_run = time.time()
    final_df_first = calculate_full_metrics(data_manager, START_DATE, END_DATE)
    end_time_first_run = time.time()
    duration_first_run = end_time_first_run - start_time_first_run
    logger.info(f"第一次執行完成，耗時: {duration_first_run:.2f} 秒。")

    assert final_df_first is not None and not final_df_first.empty, "第一次執行後，DataFrame 不應為空！"
    logger.info("斷言成功：第一次執行返回了有效的 DataFrame。")

    # 2. 驗證數據已寫入資料庫
    logger.info("\n--- 驗證資料庫寫入 ---")
    rows_in_db = check_db_content()
    assert rows_in_db > 0, "資料庫在第一次執行後不應為空！"
    logger.info("斷言成功：數據已成功寫入資料庫。")

    # 3. 第二次執行，驗證快取
    logger.info("\n--- 第二次執行 (預期從資料庫快取讀取) ---")
    start_time_second_run = time.time()
    final_df_second = calculate_full_metrics(data_manager, START_DATE, END_DATE)
    end_time_second_run = time.time()
    duration_second_run = end_time_second_run - start_time_second_run
    logger.info(f"第二次執行完成，耗時: {duration_second_run:.2f} 秒。")

    assert final_df_second is not None and not final_df_second.empty, "第二次執行後，DataFrame 不應為空！"
    logger.info("斷言成功：第二次執行返回了有效的 DataFrame。")

    # 4. 比較執行時間，驗證快取效果
    logger.info("\n--- 驗證快取效能 ---")
    # 允許一個小的容錯時間（例如 1 秒），以防網路極快或 IO 極慢的邊界情況
    cache_threshold = max(duration_first_run / 2, duration_second_run + 1)
    assert duration_second_run < cache_threshold, \
        f"快取效能未達預期！第二次執行時間 ({duration_second_run:.2f}s) " \
        f"沒有顯著快於第一次 ({duration_first_run:.2f}s)。"
    logger.info(f"斷言成功：第二次執行 ({duration_second_run:.2f}s) "
                f"顯著快於第一次 ({duration_first_run:.2f}s)，快取機制有效！")

    logger.info("\n====== 數據管道整合測試成功！ ======")


if __name__ == '__main__':
    # 檢查 API Key 是否已設定
    if "YOUR_API_KEY_HERE" in FRED_API_KEY:
        logger.error("錯誤：請設定 FRED_API_KEY 環境變數後再執行測試。")
        logger.error("例如: export FRED_API_KEY='your_real_key'")
        sys.exit(1)
    run_pipeline_test()