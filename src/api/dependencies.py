# src/api/dependencies.py
#
# --- V4 計畫書優化 (2025-09-18) ---
#
# 建立此檔案以解決循環導入問題。
#
# --- V78 重構 (2025-12-01) ---
# 在精簡計畫中，移除了獨立的 DB Manager 服務。
# 現在，這個檔案不再提供 DBClient 的實例，
# 而是直接將 db_client 這個變數作為 db.database 模組的別名。
# 這樣，其他模組可以繼續使用 db_client.some_function() 的語法，
# 無縫地從呼叫遠端 API 切換到直接呼叫本地資料庫函式。

import sys
from pathlib import Path

# 修正路徑以導入專案模組
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

# 直接將 db.database 模組賦值給 db_client 變數
from db import database as db_client

# FastAPI 的依賴注入函數現在直接回傳這個模組
def get_db():
    """FastAPI 依賴注入函數，用於提供共享的 database 模組。"""
    return db_client
