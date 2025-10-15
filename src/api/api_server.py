# api_server.py
import uuid
import shutil
import logging
import json
import subprocess
import sys
import importlib.metadata
import threading
import re
import asyncio
import os
import time
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Optional, Dict, List
from contextlib import asynccontextmanager
from urllib.parse import unquote, quote
from pydantic import BaseModel
import psutil

# --- 修正模組匯入路徑 ---
# 將專案的 src 目錄新增到 Python 的搜尋路徑中，
# 這樣才能正確找到 db.client 等模組。
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 模式設定 ---
# JULES: 改為透過環境變數來決定模擬模式，以便與 Circus 整合
# 預設為非模擬模式 (真實模式)
IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"

# V4 循環導入修復：從新的依賴檔案中導入
from .dependencies import db_client
from core import key_manager

# --- JULES 於 2025-08-09 的修改：設定應用程式全域時區 ---
# 為了確保所有日誌和資料庫時間戳都使用一致的時區，我們在應用程式啟動的
# 最早期階段就將時區環境變數設定為 'Asia/Taipei'。
os.environ['TZ'] = 'Asia/Taipei'
if sys.platform != 'win32':
    time.tzset()
# --- 時區設定結束 ---

# --- 路徑設定 ---
# 以此檔案為基準，定義專案根目錄
# 因為此檔案現在位於 src/api/ 中，所以根目錄是其上上層目錄
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# --- 主日誌設定 ---
# 主日誌器
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S%z',
    handlers=[logging.StreamHandler()] # 輸出到控制台
)
log = logging.getLogger('api_server')

def setup_database_logging():
    """設定資料庫日誌處理器。"""
    try:
        from db.log_handler import DatabaseLogHandler
        root_logger = logging.getLogger()
        # 檢查是否已經有同類型的 handler，避免重複加入
        if not any(isinstance(h, DatabaseLogHandler) for h in root_logger.handlers):
            root_logger.addHandler(DatabaseLogHandler(source='api_server'))
            log.info("資料庫日誌處理器設定完成 (source: api_server)。")
    except Exception as e:
        log.error(f"整合資料庫日誌時發生錯誤: {e}", exc_info=True)

# --- WebSocket 連線管理器 ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        log.info(f"新用戶端連線。目前共 {len(self.active_connections)} 個連線。")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        log.info(f"一個用戶端離線。目前共 {len(self.active_connections)} 個連線。")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

    async def broadcast_json(self, data: dict):
        for connection in self.active_connections:
            await connection.send_json(data)

manager = ConnectionManager()

# --- FastAPI Lifespan Manager ---
async def notification_broadcaster(app: FastAPI):
    """
    一個常駐的背景任務，專門用來監聽通知佇列，
    並將收到的訊息廣播給所有 WebSocket 用戶端。
    """
    log.info("訊息廣播員已啟動，正在監聽通知佇列...")
    while True:
        try:
            message = await app.state.notification_queue.get()
            log.info(f"📬 佇列收到訊息，準備廣播: {message.get('type', 'N/A')} (Task: {message.get('task_id', 'N/A')})")
            await app.state.manager.broadcast_json(message)
            app.state.notification_queue.task_done()
        except asyncio.CancelledError:
            log.info("訊息廣播員收到取消請求，即將關閉。")
            break
        except Exception as e:
            log.error(f"訊息廣播員發生未預期的錯誤: {e}", exc_info=True)
            await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    管理應用程式生命週期的非同步上下文管理器。
    負責在啟動時初始化資源，在關閉時進行清理。
    """
    # --- 應用程式啟動時 ---
    if not IS_MOCK_MODE:
        setup_database_logging()
        log.info("資料庫日誌處理器已透過 lifespan 事件設定。")

    queue = asyncio.Queue()
    app.state.notification_queue = queue
    log.info("全域非同步通知佇列已建立。")

    broadcaster_task = asyncio.create_task(notification_broadcaster(app))
    app.state.broadcaster_task = broadcaster_task

    log.info("[SYSTEM_READY] All modules are fully initialized.")
    yield

    # --- 應用程式關閉時 ---
    log.info("正在關閉應用程式...")
    app.state.broadcaster_task.cancel()
    try:
        await app.state.broadcaster_task
    except asyncio.CancelledError:
        log.info("訊息廣播員已成功關閉。")

# --- FastAPI 應用實例 ---
app = FastAPI(title="鳳凰音訊轉錄儀 API (v3 - 重構)", version="3.0", lifespan=lifespan)
app.state.manager = manager
# --- 全域信號量設定 ---
app.state.analysis_semaphore = asyncio.Semaphore(3)
app.state.download_semaphore = asyncio.Semaphore(5)
app.state.processing_semaphore = asyncio.Semaphore(2)

# --- 中介軟體 (Middleware) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_server_port_to_state(request: Request, call_next):
    if not hasattr(request.app.state, 'server_port'):
        server = request.scope.get("server")
        if server and len(server) > 1:
            port = server[1]
            request.app.state.server_port = port
            log.info(f"✅ 成功從 ASGI Scope 捕獲並設定伺服器埠號: {port}")
    response = await call_next(request)
    return response

# --- 整合模組化路由 ---
from core import config_manager
from api.routes import (
    ui, page1, page2_downloader, page3_processor, page4_analyzer,
    page5_backup, page6_keys, page7_prompts, page8_details, page9_dashboard,
    page10_test, system, bond_service_proxy, line_workflow_api,
    line_data_api
)

app.state.config = config_manager.get_config()
log.info(f"全域設定已載入。API 超時設定為: {app.state.config.get('api_timeout_seconds')} 秒。")

# UI 路由
app.include_router(ui.router, tags=["UI"])
# API 路由
app.include_router(system.router)
app.include_router(page1.router)
app.include_router(page2_downloader.router, prefix="/api/downloader", tags=["API: 批次下載"])
app.include_router(page3_processor.router, prefix="/api/processor", tags=["API: 檔案處理"])
app.include_router(page4_analyzer.router, prefix="/api/analyzer", tags=["API: AI 分析"])
app.include_router(page5_backup.router, prefix="/api/backup", tags=["API: 備份管理"])
app.include_router(page6_keys.router, prefix="/api/keys", tags=["API: 金鑰管理"])
app.include_router(page7_prompts.router, tags=["API: 提示詞管理"])
app.include_router(page8_details.router, prefix="/api", tags=["API: 檔案總覽"])
app.include_router(page9_dashboard.router, prefix="/api/dashboard", tags=["API: 績效儀表板"])
app.include_router(page10_test.router, prefix="/api/service_test", tags=["API: 微服務測試"])
app.include_router(line_workflow_api.router)
app.include_router(line_data_api.router)
# 債券服務代理
app.include_router(bond_service_proxy.router, prefix="/api/bond_service", tags=["API: Bond Service Proxy"])
app.include_router(bond_service_proxy.page_router, tags=["UI: Bond Service Pages"])

# --- 路徑設定 ---
UPLOADS_DIR = ROOT_DIR / "uploads"
REPORTS_DIR = ROOT_DIR / "reports"
DOWNLOADS_DIR = ROOT_DIR / "downloads"
STATIC_DIR = ROOT_DIR / "src" / "static"

UPLOADS_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)
DOWNLOADS_DIR.mkdir(exist_ok=True)
if not STATIC_DIR.exists():
    log.warning(f"靜態檔案目錄 {STATIC_DIR} 不存在，前端頁面可能無法載入。")
else:
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")
    app.mount("/downloads", StaticFiles(directory=DOWNLOADS_DIR), name="downloads")

@app.get("/media/{file_path:path}")
async def serve_media_files(file_path: str):
    try:
        decoded_path = unquote(file_path)
        safe_path = os.path.normpath(os.path.join(UPLOADS_DIR, decoded_path))
        if not safe_path.startswith(str(UPLOADS_DIR)):
             raise HTTPException(status_code=403, detail="禁止存取。")
        if os.path.exists(safe_path) and os.path.isfile(safe_path):
            return FileResponse(safe_path)
        else:
            log.warning(f"請求的媒體檔案不存在: {safe_path}")
            return JSONResponse(status_code=404, content={"detail": "File not found"})
    except Exception as e:
        log.error(f"服務媒體檔案時發生錯誤: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": str(e)})

# ... (其他 API 端點保持不變) ...

# --- 主程式啟動 ---
if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="鳳凰音訊轉錄儀 API 伺服器")
    parser.add_argument("--port", type=int, default=8001, help="伺服器監聽的埠號")
    args, _ = parser.parse_known_args()

    log.info("🚀 啟動 API 伺服器 (v3)...")
    log.info(f"請在瀏覽器中開啟 http://127.0.0.1:{args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)