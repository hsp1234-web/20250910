# api_server.py
import logging
import json
import sys
import os
import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from contextlib import asynccontextmanager

# --- 修正模組匯入路徑 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 時區設定 ---
os.environ['TZ'] = 'Asia/Taipei'
if sys.platform != 'win32':
    time.tzset()

# --- 路徑設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = ROOT_DIR / "src" / "static"

# --- 主日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S%z',
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger('api_server')

# --- 樣板引擎設定 ---
templates = Jinja2Templates(directory=str(STATIC_DIR))

def setup_database_logging():
    try:
        from db.log_handler import DatabaseLogHandler
        root_logger = logging.getLogger()
        if not any(isinstance(h, DatabaseLogHandler) for h in root_logger.handlers):
            root_logger.addHandler(DatabaseLogHandler(source='api_server'))
            log.info("資料庫日誌處理器設定完成 (source: api_server)。")
    except Exception as e:
        log.error(f"整合資料庫日誌時發生錯誤: {e}", exc_info=True)

# --- FastAPI Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_database_logging()
    log.info("資料庫日誌處理器已透過 lifespan 事件設定。")
    yield

# --- FastAPI 應用實例 ---
app = FastAPI(title="鳳凰系統 API (v3.2 - 模組化)", version="3.2", lifespan=lifespan)

# --- 中介軟體 (Middleware) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 整合模組化路由 ---
from api.routes import ui, page1_ingestion, page2_downloader, page3_processor, page4_analyzer, page5_backup, page6_keys, page7_prompts, websockets

app.include_router(ui.router, tags=["UI"])
app.include_router(page1_ingestion.router, prefix="/api/ingestion", tags=["API: 網址提取"])
app.include_router(page2_downloader.router, prefix="/api/downloader", tags=["API: 批次下載"])
app.include_router(page3_processor.router, prefix="/api/processor", tags=["API: 檔案處理"])
app.include_router(page4_analyzer.router, prefix="/api/analyzer", tags=["API: AI 分析"])
app.include_router(page5_backup.router, prefix="/api/backup", tags=["API: 備份管理"])
app.include_router(page6_keys.router, prefix="/api", tags=["API: 金鑰管理"])
app.include_router(page7_prompts.router, prefix="/api", tags=["API: 提示詞管理"])
# 新增模組化的 WebSocket 路由
app.include_router(websockets.router, tags=["API: WebSockets"])


# --- 靜態檔案與路徑設定 ---
REPORTS_DIR = ROOT_DIR / "reports"
DOWNLOADS_DIR = ROOT_DIR / "downloads"
REPORTS_DIR.mkdir(exist_ok=True)
DOWNLOADS_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")
app.mount("/downloads", StaticFiles(directory=DOWNLOADS_DIR), name="downloads")


# --- 其他 API 端點 ---

@app.get("/", response_class=HTMLResponse)
async def serve_main_page(request: Request):
    return templates.TemplateResponse("main.html", {"request": request})

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "API Server is running."}

# --- 主程式啟動 ---
if __name__ == "__main__":
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser(description="鳳凰系統 API 伺服器")
    parser.add_argument("--port", type=int, default=8001, help="伺服器監聽的埠號")
    args, _ = parser.parse_known_args()
    log.info("🚀 啟動 API 伺服器...")
    log.info(f"請在瀏覽器中開啟 http://127.0.0.1:{args.port}")
    uvicorn.run("api_server:app", host="0.0.0.0", port=args.port, reload=True)
