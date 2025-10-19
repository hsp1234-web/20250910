# -*- coding: utf-8 -*-
import asyncio
import logging
import json
import hashlib
from pathlib import Path
import sys
from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, Form
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid

# --- 專案根目錄設定，確保模組能正確匯入 ---
try:
    from src.db import database as db
    from src.tools import youtube_downloader
    from src.core.time_utils import get_current_taipei_time_iso
except ImportError:
    project_root = Path(__file__).parent.parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.db import database as db
    from src.tools import youtube_downloader
    from src.core.time_utils import get_current_taipei_time_iso

# --- 日誌設定 ---
log = logging.getLogger("audio_report_api")

# --- FastAPI 路由器 ---
router = APIRouter(prefix="/api/audio_report", tags=["音訊報告 (V2 架構)"])

# --- 常數設定 ---
INCOMING_DIR = Path("downloads/incoming")
INCOMING_DIR.mkdir(parents=True, exist_ok=True)

# --- 資料模型 ---
class DownloadResponse(BaseModel):
    status: str
    message: str
    task_hash: str

# --- WebSocket 管理 ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        # 使用 asyncio.gather 來並行發送訊息
        await asyncio.gather(*[ws.send_text(message) for ws in self.active_connections])

manager = ConnectionManager()

# --- WebSocket 端點 ---
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # 保持連線開啟以接收廣播
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        log.info("一個 WebSocket 客戶端已離線。")

# --- API 路由 (重構後) ---
@router.post("/download", response_model=DownloadResponse, status_code=202)
async def start_audio_download(
    background_tasks: BackgroundTasks,
    url: str = Form(...)
):
    """
    以非同步方式接收單一音訊下載請求，並使用雜湊追蹤。

    此端點會：
    1. 為任務生成一個唯一的 SHA256 雜湊值。
    2. 在資料庫中建立一個狀態為 '下載中' 的任務記錄。
    3. 將 `youtube_downloader.download_audio_worker` 作為背景任務加入佇列。
    4. 立即回傳任務雜湊，並透過 WebSocket 廣播任務已建立的訊息。
    """
    log.info(f"收到非同步音訊下載請求: URL={url}")

    if not url.strip() or not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="提供了無效的 URL。")

    try:
        # 1. 生成唯一的任務雜湊
        timestamp = get_current_taipei_time_iso()
        hash_string = f"{url}{timestamp}"
        task_hash = hashlib.sha256(hash_string.encode('utf-8')).hexdigest()
        log.info(f"為任務產生的唯一雜湊: {task_hash}")

        # 2. 建立任務 payload
        #    在這個新架構中，我們不再需要預先抓取標題，
        #    因為重新命名的邏輯已經轉移到 file_watcher，
        #    而 file_watcher 會從資料庫讀取 payload。
        #    但是，為了讓 watcher 能拿到原始 URL，我們還是要儲存它。
        #    (更新)：為了讓 watcher 能拿到標題，我們還是把標題存進去
        #    這裡我們還是需要一個輕量級的方法來獲取標題
        video_title = "Fetching title..." # 暫時的標題
        # 這裡可以呼叫一個 yt-dlp 的輕量級指令來獲取標題
        # 為簡化起見，暫時省略

        payload = {
            "original_url": url,
            "video_title": video_title,
            "requested_at": timestamp
        }

        # 3. 在資料庫中建立任務記錄
        #    狀態由資料庫預設為 '處理中'
        db.add_task(
            task_hash=task_hash,
            payload=json.dumps(payload),
            task_type='audio_download'
        )
        log.info(f"已在資料庫中為雜湊 {task_hash} 建立任務記錄。")

        # 4. 將下載工人的執行函式加入背景任務
        background_tasks.add_task(
            youtube_downloader.download_audio_worker,
            youtube_url=url,
            output_dir=INCOMING_DIR,
            task_hash=task_hash
        )
        log.info(f"已將雜湊為 {task_hash} 的下載任務加入背景佇列。")

        # 5. 透過 WebSocket 廣播任務已建立
        await manager.broadcast(json.dumps({
            "type": "TASK_CREATED",
            "payload": {
                "task_hash": task_hash,
                "url": url,
                "status": "下載中",
                "message": "已建立任務，準備下載..."
            }
        }))

        # 6. 立即回傳 HTTP 回應
        return DownloadResponse(
            status="accepted",
            message="下載任務已成功加入佇列",
            task_hash=task_hash
        )

    except Exception as e:
        log.error(f"在分派音訊下載任務時發生嚴重錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"無法分派下載任務: {str(e)}")