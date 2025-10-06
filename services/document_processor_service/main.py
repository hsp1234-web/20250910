import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI

# --- 路徑修正，確保能找到服務模組 ---
# 將專案根目錄加入到 Python 的搜尋路徑中，以解決在協調器環境下的相對匯入問題。
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# --- 本地模組匯入 (使用絕對路徑) ---
from services.document_processor_service.api_routes import router as api_router
from services.document_processor_service.repository import initialize_database

# --- 日誌基礎設定 ---
# 確保在應用程式啟動時，日誌記錄器就被設定好
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=logging.StreamHandler()
)
log = logging.getLogger(__name__)

# --- FastAPI 生命週期事件 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    管理應用程式生命週期的非同步上下文管理器。
    - 在應用程式啟動前執行: 初始化資料庫。
    - 在應用程式關閉後執行: (目前無操作，可擴充)
    """
    log.info("服務啟動中...")
    initialize_database()
    log.info("資料庫已成功初始化。")
    yield
    log.info("服務關閉中...")

# --- FastAPI 應用程式實例化 ---
app = FastAPI(
    title="文件智慧處理微服務 (Document Processor Service)",
    description="一個用於下載、拆解、並使用本地 AI 分析文件的獨立微服務。",
    version="1.0.0",
    lifespan=lifespan # 註冊生命週期事件
)

# --- 包含 API 路由 ---
# 將我們在 api_routes.py 中定義的所有端點加入到主應用程式中
app.include_router(api_router)

# --- 根端點 ---
@app.get("/")
async def read_root():
    """提供一個簡單的根端點，說明服務用途。"""
    return {"message": "歡迎使用文件智慧處理微服務。請使用 /docs 查看 API 文件。"}