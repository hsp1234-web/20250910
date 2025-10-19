# -*- coding: utf-8 -*-
import asyncio
import logging
import json
import hashlib
from pathlib import Path
import sys
from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid

# --- 專案根目錄設定，確保模組能正確匯入 ---
try:
    from src.db import database as db
    from src.core.time_utils import get_current_taipei_time_iso
    from src.core.sse_manager import sse_manager
    from src.core.download_worker import task_queue # <-- 匯入任務佇列
except ImportError:
    project_root = Path(__file__).parent.parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.db import database as db
    from src.core.time_utils import get_current_taipei_time_iso
    from src.core.sse_manager import sse_manager
    from src.core.download_worker import task_queue # <-- 匯入任務佇列

# --- 日誌設定 ---
log = logging.getLogger("audio_report_api")

# --- FastAPI 路由器 ---
router = APIRouter(prefix="/api/audio_report", tags=["音訊報告 (V2 架構)"])

# --- 常數設定 ---
INCOMING_DIR = Path("downloads/incoming")
INCOMING_DIR.mkdir(parents=True, exist_ok=True)

# --- 資料模型 ---
class AudioDownloadRequest(BaseModel):
    url: str

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
@router.get("/stream-status/{task_hash}")
async def stream_status(task_hash: str):
    """
    提供一個 SSE 端點，用於即時串流特定任務的狀態更新。
    """
    return EventSourceResponse(sse_manager.subscribe(task_hash))

@router.post("/download", response_model=DownloadResponse, status_code=202)
async def start_audio_download(request: AudioDownloadRequest):
    """
    接收音訊下載請求，將其放入應用內佇列，並立即回傳。
    """
    url = request.url
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

        # 4. 建立任務物件並放入佇列
        task_to_queue = {
            "task_hash": task_hash,
            "payload": json.dumps(payload)
        }
        task_queue.put(task_to_queue)
        log.info(f"已將任務 {task_hash} 加入下載佇列。")

        # 5. 透過 SSE 發布任務已建立的初始狀態
        await sse_manager.publish(task_hash, json.dumps({
            "status": "queued",
            "message": "任務已成功排入佇列，等待工人處理..."
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