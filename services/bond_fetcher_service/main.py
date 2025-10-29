# services/bond_fetcher_service/main.py
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

from .repository import DataFetcherRepository, initialize_database

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 全域變數 ---
# 為了依賴注入，我們在 lifespan 中設定 repository 實例
repository: DataFetcherRepository

class FetchRequest(BaseModel):
    """定義資料抓取請求的內容格式。"""
    indicators: List[str]
    start_date: str
    end_date: str

def run_fetching_task(repo: DataFetcherRepository, indicators: List[str], start_date: str, end_date: str):
    """
    同步的背景任務函式，負責迭代並抓取所有請求的指標。
    """
    logger.info(f"背景任務已啟動，準備抓取 {len(indicators)} 個指標...")
    all_indicators = repo.get_all_indicator_names()

    success_count = 0
    failure_count = 0

    for indicator in indicators:
        if indicator in all_indicators:
            try:
                if repo.fetch_and_store_series(indicator, start_date, end_date):
                    success_count += 1
                else:
                    failure_count += 1
            except Exception as e:
                logger.error(f"背景抓取指標 '{indicator}' 時發生未預期錯誤: {e}", exc_info=True)
                failure_count += 1
        else:
            logger.warning(f"請求了未知的指標 '{indicator}'，已跳過。")

    logger.info(f"背景抓取任務完成。成功: {success_count}，失敗: {failure_count}。")

# --- 應用程式生命週期 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """處理應用程式啟動事件。"""
    global repository
    logger.info("債券資料抓取服務 (bond_fetcher_service) 啟動中...")

    # 1. 初始化資料庫 (確保資料表存在)
    initialize_database()

    # 2. 建立倉儲實例以供後續使用
    repository = DataFetcherRepository()

    logger.info("✅ 債券資料抓取服務已就緒。")
    yield
    logger.info("債券資料抓取服務已關閉。")

# --- FastAPI 應用程式實例 ---
app = FastAPI(
    lifespan=lifespan,
    title="債券資料抓取服務 (Bond Fetcher Service)",
    description="一個專門用於從外部來源抓取並儲存金融數據的獨立微服務。",
    version="1.0.0",
)

# --- API 端點 ---
@app.post("/api/fetch")
async def fetch_data(request: FetchRequest, background_tasks: BackgroundTasks):
    """
    接收資料抓取請求，並將其放入背景任務中執行。
    此端點會立即返回，不會等待抓取完成。
    """
    if not request.indicators:
        raise HTTPException(status_code=400, detail="必須提供至少一個指標進行抓取。")

    logger.info(f"收到抓取請求，包含 {len(request.indicators)} 個指標。")

    # 將耗時的抓取任務加入到背景執行
    background_tasks.add_task(
        run_fetching_task,
        repository,
        request.indicators,
        request.start_date,
        request.end_date
    )

    return {"message": "資料抓取任務已在背景啟動。"}

@app.get("/health")
async def health_check():
    """提供一個簡單的健康檢查端點。"""
    return {"status": "ok"}

@app.get("/api/indicators")
async def get_available_indicators():
    """返回所有可用的指標名稱列表。"""
    return {"indicators": repository.get_all_indicator_names()}
