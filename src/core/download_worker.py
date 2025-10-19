# src/core/download_worker.py
import logging
import queue
import threading
import time
import asyncio

# 確保能從根目錄正確匯入
import sys
from pathlib import Path
try:
    from src.tools import youtube_downloader
except ImportError:
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.tools import youtube_downloader

# --- 日誌設定 ---
log = logging.getLogger('DownloadWorker')

# --- 全域任務佇列 ---
task_queue = queue.Queue()

# --- 工人執行緒 ---
def worker():
    """
    一個長期運作的工人函式，負責從佇列中獲取並處理任務。
    """
    log.info("👷‍♂️ 下載工人執行緒已啟動，準備接收任務...")
    # 為這個執行緒建立一個新的事件迴圈
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            task = task_queue.get(block=True)

            if task is None:
                log.info("👷‍♂️ 工人收到停止信號 (毒丸)，準備退出...")
                break # 退出 while 迴圈

            log.info(f"📦 工人收到新任務: {task}")

            # 使用 loop.run_until_complete 來執行我們的非同步任務函式
            loop.run_until_complete(youtube_downloader.execute_full_download_workflow(task))

            log.info(f"✅ 任務處理完成: {task}")

            task_queue.task_done()

        except Exception as e:
            log.error(f"處理任務時發生嚴重錯誤: {e}", exc_info=True)
            if 'task' in locals() and task is not None:
                task_queue.task_done()

    loop.close()
    log.info("👷‍♂️ 下載工人執行緒已乾淨地關閉。")


def start_worker_thread():
    """
    建立並啟動工人執行緒。
    """
    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()
    log.info("🚀 已成功啟動背景下載工人執行緒。")
    return worker_thread