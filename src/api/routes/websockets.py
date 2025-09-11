# src/api/routes/websockets.py
import logging
import json
import sys
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.websocket_manager import manager as ws_manager

log = logging.getLogger(__name__)
router = APIRouter()

# --- WebSocket 端點 ---

@router.websocket("/ws/status")
async def websocket_status_endpoint(websocket: WebSocket):
    """
    WebSocket 端點，專門用於廣播任務狀態。
    前端應連線到此端點以接收即時更新。
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # 這個端點主要是用來廣播的，所以我們只需要保持連線
            # FastAPI 會自動處理 ping/pong 來維持連線
            # 設置一個 receive_text() 來保持連線開放，但我們不處理收到的任何訊息。
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        log.info("一個狀態監聽 WebSocket 用戶端已離線。")

# --- 內部 API 端點 ---

class NotifyPayload(BaseModel):
    taskId: int
    status: str
    message: str
    progress: int

@router.post("/internal/notify_status")
async def notify_status_update(payload: NotifyPayload):
    """
    一個內部端點，供背景 Worker 程序呼叫，
    以便透過 WebSocket 將進度更新廣播給前端。
    """
    log.info(f"🔔 收到內部狀態更新通知: {payload.dict()}")
    message = {
        "type": "STATUS_UPDATE",
        "payload": payload.dict()
    }
    await ws_manager.broadcast(json.dumps(message))
    return {"status": "notification_sent"}
