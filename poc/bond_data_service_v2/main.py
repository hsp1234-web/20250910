# poc/bond_data_service_v2/main.py
# 繁體中文註解：應用程式主啟動器

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 導入我們重構後的模組
from . import api_routes, database, globals
from .repository import DataRepository
from .service import StressIndexService

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 背景任務 ---
# 注意：背景任務的邏輯也將在後續步驟中被重構到 service 層
last_broadcasted_timestamp = None
async def periodic_data_updater():
    """
    定期在背景檢查是否有新的數據點，並透過 SSE 廣播。
    (這部分邏輯未來會移到 service 層)
    """
    global last_broadcasted_timestamp
    await asyncio.sleep(15)
    while True:
        try:
            # 這裡的邏輯暫時保留，直到 service 層建立完畢
            pass # 暫時停用以避免複雜性
        except Exception as e:
            logger.error(f"背景數據更新任務發生錯誤: {e}", exc_info=True)
        await asyncio.sleep(300)

# --- 應用程式生命週期管理 (Lifespan) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    在應用程式啟動和關閉時執行的非同步上下文管理器。
    """
    logger.info("債券資料服務啟動中...")

    # 初始化資料庫
    database.initialize_database()

    # 初始化倉儲層和服務層
    globals.data_repository = DataRepository()
    globals.stress_index_service = StressIndexService(globals.data_repository)
    globals.sse_connections = []

    # 啟動背景任務 (暫時保留)
    update_task = asyncio.create_task(periodic_data_updater())

    yield

    # 應用程式關閉時執行的清理工作
    logger.info("正在關閉背景更新任務...")
    update_task.cancel()
    try:
        await update_task
    except asyncio.CancelledError:
        logger.info("背景更新任務已成功取消。")

    logger.info("債券資料服務已關閉。")


# --- FastAPI 應用程式實例 ---
app = FastAPI(
    lifespan=lifespan,
    title="債券與一級交易商分析服務 (重構版)",
    description="一個提供債券相關宏觀經濟數據，並計算與呈現一級交易商壓力指數相關圖表的微服務。",
    version="2.0.0",
)

# --- 中介軟體 (Middleware) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 掛載靜態檔案與 API 路由 ---
# 從 globals 模組中獲取靜態檔案目錄的路徑
app.mount("/static", StaticFiles(directory=globals.STATIC_DIR), name="static")

# 包含從 api_routes.py 中定義的所有路由
app.include_router(api_routes.router)

logger.info("FastAPI 應用程式已成功設定。")