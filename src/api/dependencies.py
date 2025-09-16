# src/api/dependencies.py
#
# --- V4 計畫書優化 (2025-09-18) ---
#
# 建立此檔案以解決循環導入問題。
#
# 問題：
# `api_server.py` 導入了 `routes` 中的模組 (例如 `page2_downloader`)，
# 而這些路由模組又需要從 `api_server.py` 導入共享的 `get_db` 依賴項，
# 這導致了 Python 的循環導入錯誤 (Circular Import Error)。
#
# 解決方案：
# 將共享的依賴項 (db_client 實例和 get_db 函數) 移到這個獨立的 `dependencies.py` 檔案中。
# 現在，`api_server.py` 和所有的路由模組都從這個檔案導入依賴，從而打破了依賴迴圈。

import sys
from pathlib import Path

# 修正路徑以導入專案模組
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from db.client import DBClient

# 建立一個全域共享的 DBClient 實例。
# 這個實例及其底層的 httpx.Client 連線池將在整個應用程式的生命週期中被重複使用。
db_client = DBClient()

def get_db() -> DBClient:
    """FastAPI 依賴注入函數，用於提供共享的 db_client 實例。"""
    return db_client
