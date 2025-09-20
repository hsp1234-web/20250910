# -*- coding: utf-8 -*-
"""
債券分析微服務主入口點 (Main Entry Point)

功能：
- 建立 FastAPI 應用實例。
- 在應用啟動時初始化資料庫 (建立表格)。
- 掛載 API 路由。
- 定義根端點。
"""

import logging
from fastapi import FastAPI

# 導入內部模組
from .db import database
from .api import routes

# --- 日誌基礎設定 ---
# 建議在實際部署時使用更進階的日誌設定 (如 loguru 或 JSON logger)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- 初始化資料庫 ---
# 這將根據 models.py 中的定義建立資料庫檔案和表格 (如果尚不存在)
try:
    database.init_db()
    logging.info("資料庫初始化成功。")
except Exception as e:
    logging.critical(f"資料庫初始化失敗: {e}", exc_info=True)
    # 在實際應用中，這裡可能需要終止啟動

# --- 建立 FastAPI 應用 ---
app = FastAPI(
    title="債券分析微服務",
    description="一個用於執行一級交易商壓力分析的獨立微服務。",
    version="1.0.0"
)

# --- 掛載 API 路由 ---
# 將 api/routes.py 中定義的所有端點包含進來
app.include_router(routes.router, prefix="/api", tags=["Analysis"])

# --- 定義根端點 ---
@app.get("/", tags=["Root"])
def read_root():
    """
    一個簡單的根端點，用於確認服務是否正在運行。
    """
    return {"message": "歡迎使用債券分析微服務。請訪問 /docs 查看 API 文件。"}

# --- (可選) Uvicorn 啟動設定 ---
# 這段程式碼允許你透過 `python -m services.bond_service.main` 來啟動服務
# 但在生產環境中，通常會使用 Gunicorn + Uvicorn Worker。
if __name__ == "__main__":
    import uvicorn
    # 注意：reload=True 只應在開發環境中使用
    uvicorn.run("services.bond_service.main:app", host="0.0.0.0", port=8001, reload=True)
