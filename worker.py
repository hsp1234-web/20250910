#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import logging
from pathlib import Path

from rq import Connection, Worker

# --- 路徑設定 ---
# 將專案的根目錄 (本檔案的上層) 新增到 Python 的搜尋路徑中
# 這是為了確保 worker 能夠正確地找到 src 下的模組，例如 src.core.queue
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

# --- 日誌設定 ---
# 讓 worker 的日誌輸出格式與協調器保持一致
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
log = logging.getLogger('worker')


# --- 匯入我們自己的模組 ---
# 必須在設定好 sys.path 之後才能匯入
try:
    from src.core.queue import analysis_queue, redis_conn
except ImportError as e:
    log.critical(f"無法從 src.core.queue 匯入模組。請確保路徑設定正確且檔案存在。錯誤: {e}")
    sys.exit(1)


if __name__ == '__main__':
    log.info("--- [Worker 啟動] ---")
    log.info(f"監聽的佇列: {[q.name for q in [analysis_queue]]}")

    # 使用 with Connection(redis_conn) 確保在 worker 的生命週期內使用同一個 Redis 連線。
    # 這是一個推薦的最佳實踐。
    with Connection(redis_conn):
        # 建立一個 Worker，並告訴它要監聽 'analysis_queue'
        # 我們也可以傳遞一個包含多個佇列名稱的列表，例如 ['high', 'default', 'low']
        w = Worker([analysis_queue])

        # 啟動 worker。它會開始從佇列中拉取並執行任務。
        # burst=True 模式會在處理完所有現有任務後退出，適合測試。
        # 預設 (burst=False) 則會持續運行，監聽新任務。
        w.work(with_scheduler=True)

    log.info("--- [Worker 已停止] ---")
