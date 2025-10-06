import logging
import sys
from pathlib import Path
from fastapi import FastAPI

# --- 路徑修正，確保能找到服務模組 ---
# 將專案根目錄加入到 Python 的搜尋路徑中，以解決在協調器環境下的相對匯入問題。
# services/stock_id_extractor_service/ -> services/ -> . (root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# --- 本地模組匯入 (使用絕對路徑) ---
from services.stock_id_extractor_service.api_routes import router as api_router

# --- 日誌基礎設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=logging.StreamHandler()
)

# --- FastAPI 應用程式實例化 ---
app = FastAPI(
    title="股票代號提取器微服務 (Stock ID Extractor Service)",
    description="一個使用非 AI 技術，從文字中精確提取有效台股股票代號的 POC 微服務。",
    version="1.0.0"
)

# --- 包含 API 路由 ---
app.include_router(api_router)

# --- 根端點 ---
@app.get("/")
async def read_root():
    """提供一個簡單的根端點，說明服務用途。"""
    return {"message": "歡迎使用股票代號提取器微服務。請使用 /docs 查看 API 文件。"}