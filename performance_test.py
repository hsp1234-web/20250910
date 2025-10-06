import asyncio
import logging
import sys
import time
import resource
from pathlib import Path

# --- 路徑修正與日誌設定 ---
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# --- 匯入我們的服務模組 ---
from services.document_processor_service.processor import process_document_url
from services.document_processor_service.repository import create_processing_task, initialize_database

# --- 測試目標 ---
TEST_URL = "https://drive.google.com/file/d/1ADg9NnB10z3qjnSZPOn6BLh_Fz8wjY9T/view?usp=sharing"

async def main():
    """
    執行一次端到端的效能測試，並在內部測量時間與資源消耗。
    """
    log = logging.getLogger("PerformanceTest")
    log.info("--- 開始執行端到端效能測試 ---")
    log.info(f"測試目標 URL: {TEST_URL}")

    # --- 效能監控：前置作業 ---
    start_time = time.monotonic()
    start_rusage = resource.getrusage(resource.RUSAGE_SELF)

    # 步驟 1: 確保資料庫和資料表已存在
    log.info("步驟 1/3: 初始化資料庫...")
    initialize_database()

    # 步驟 2: 在資料庫中建立一個待處理的任務
    log.info("步驟 2/3: 建立處理任務...")
    if not create_processing_task(TEST_URL):
        log.warning("任務已存在，將直接執行處理。")

    # 步驟 3: 執行核心處理流程
    log.info("步驟 3/3: 執行核心文件處理流程...")
    await process_document_url(TEST_URL)

    # --- 效能監控：後置作業與報告 ---
    end_rusage = resource.getrusage(resource.RUSAGE_SELF)
    end_time = time.monotonic()

    # 計算效能指標
    elapsed_time = end_time - start_time
    user_cpu_time = end_rusage.ru_utime - start_rusage.ru_utime
    system_cpu_time = end_rusage.ru_stime - start_rusage.ru_stime
    # ru_maxrss 在 Linux 上回報的是 Kilobytes，我們將其轉換為 MB
    max_memory_mb = end_rusage.ru_maxrss / 1024

    # 產生並印出報告
    log.info("--- 端到端效能測試執行完畢 ---")
    print("\n" + "="*50)
    print("           效能與資源消耗報告")
    print("="*50)
    print(f"  總執行時間 (Wall clock): {elapsed_time:.2f} 秒")
    print(f"  CPU 使用時間 (User):    {user_cpu_time:.2f} 秒")
    print(f"  CPU 使用時間 (System):  {system_cpu_time:.2f} 秒")
    print(f"  峰值記憶體使用量:         {max_memory_mb:.2f} MB")
    print("="*50)


if __name__ == "__main__":
    asyncio.run(main())