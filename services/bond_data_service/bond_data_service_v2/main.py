# poc/bond_data_service_v2/main.py

import logging
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 匯入重構後的新架構
from . import api_routes
from .repository import FinancialDataRepository, initialize_database
from .service import StressIndexService

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 背景任務 ---
async def periodic_data_updater(service: StressIndexService):
    """
    定期在背景檢查是否有新的數據點，並協調廣播。
    """
    await asyncio.sleep(15) # 啟動後延遲

    while True:
        try:
            logger.info("背景任務 (v2.1)：呼叫服務層檢查更新...")
            # 服務層現在會返回需要廣播的數據，或 None
            update_payload = service.check_for_updates()

            if update_payload:
                logger.info(f"背景任務：從服務層收到更新 payload，準備交由 API 層廣播。")
                # 將 payload 交給 API 層的廣播函式
                await api_routes.broadcast_update(update_payload)
            else:
                logger.info("背景任務：服務層回報無新數據。")

        except Exception as e:
            logger.error(f"背景數據更新任務發生錯誤: {e}", exc_info=True)

        await asyncio.sleep(300) # 等待 5 分鐘

# --- 應用程式生命週期 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    處理應用程式啟動和關閉事件，並設定好依賴注入。
    """
    logger.info("債券資料服務 (v2.1) 啟動中...")

    # 1. 初始化資料庫
    initialize_database()

    # 2. 建立倉儲和服務實例
    repository = FinancialDataRepository()
    service = StressIndexService(repository)

    # 3. 將 service 實例注入到 API 路由模組中
    api_routes.service = service

    # 4. 啟動背景任務
    update_task = asyncio.create_task(periodic_data_updater(service))

    yield

    # --- 關閉邏輯 ---
    logger.info("正在關閉背景更新任務...")
    update_task.cancel()
    try:
        await update_task
    except asyncio.CancelledError:
        logger.info("背景更新任務已成功取消。")
    logger.info("債券資料服務已關閉。")

# --- FastAPI 應用實例化 ---
app = FastAPI(
    lifespan=lifespan,
    title="債券與一級交易商分析服務 (v2.1 Refactored)",
    description="採用分層架構的重構版本，提供債券相關宏觀經濟數據與壓力指數分析。",
    version="2.1.0",
)

# --- CORS 中間件 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 包含 API 路由 ---
app.include_router(api_routes.router)