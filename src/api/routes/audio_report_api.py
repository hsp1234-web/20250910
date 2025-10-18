# -*- coding: utf-8 -*-
import asyncio
import logging
from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
import json
from pathlib import Path
import sys
import subprocess

# --- 專案模組導入 ---
from src.db.client import DBClient
db_client = DBClient()

# --- 日誌設定 ---
log = logging.getLogger("audio_report_api")

# --- FastAPI 路由器 ---
router = APIRouter(prefix="/api/audio_report", tags=["Audio Report"])

# --- 資料模型 (更新) ---
class DownloadRequest(BaseModel):
    urls: List[str] = Field(..., description="要下載的 URL 列表。")
    download_type: str = Field("audio", description="下載類型：'audio' 或 'video'。")
    audio_format: Optional[str] = Field("m4a", description="音訊格式，例如 'm4a', 'mp3'。")
    video_resolution: Optional[str] = Field("best", description="影片解析度，例如 '1080p', '720p'。")

class TaskResponse(BaseModel):
    task_id: str
    url: str
    message: str

# --- 靜態路徑設定 (更新) ---
AUDIO_DIR = Path("downloads/audio")
VIDEO_DIR = Path("downloads/video")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

# --- WebSocket 管理 ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    async def broadcast(self, message: str):
        await asyncio.gather(*[ws.send_text(message) for ws in self.active_connections])

manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        log.info("一個 WebSocket 客戶端已離線。")

async def broadcast_status(task_id: str, url: str, status: str, **kwargs):
    payload = {"task_id": task_id, "url": url, "status": status, **kwargs}
    message_json = json.dumps({"type": "DOWNLOAD_STATUS", "payload": payload})
    await manager.broadcast(message_json)

# --- 背景任務 (更新) ---
async def run_download_task(task_id: str, url: str, download_type: str, audio_format: str, video_resolution: str):
    log.info(f"任務 {task_id}: 開始處理 URL: {url} (類型: {download_type})")
    await broadcast_status(task_id, url, "starting", message=f"已建立任務，準備下載 {download_type}...")
    db_client.update_task_status(task_id, 'processing', json.dumps({"detail": "下載中..."}))

    try:
        output_dir = VIDEO_DIR if download_type == "video" else AUDIO_DIR
        command = [
            sys.executable, "-u", "src/tools/youtube_downloader.py",
            "--url", url, "--output-dir", str(output_dir),
            "--download-type", download_type,
            "--audio-format", audio_format,
            "--video-resolution", video_resolution
        ]

        log.info(f"任務 {task_id}: 執行指令: {' '.join(command)}")
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_message = stderr.decode('utf-8', errors='ignore').strip()
            log.error(f"任務 {task_id} 失敗。返回碼: {process.returncode}。錯誤: {error_message}")
            await broadcast_status(task_id, url, "failed", message=error_message)
            db_client.update_task_status(task_id, 'failed', json.dumps({"error": error_message}))
            return

        result = json.loads(stdout.decode('utf-8'))
        log.info(f"任務 {task_id} 成功完成。結果: {result}")

        output_path = Path(result["output_path"])
        preview_url = f"/downloads/{download_type}/{output_path.name}"

        # 將最終結果存入資料庫
        final_payload = {
            "message": f"檔案 '{result.get('video_title', 'N/A')}' 下載成功。",
            "filename": output_path.name,
            "video_title": result.get("video_title"),
            "output_path": str(output_path),
            "preview_url": preview_url
        }
        db_client.update_task_status(task_id, 'completed', json.dumps(final_payload))

        # 廣播成功訊息
        await broadcast_status(task_id, url, "completed", **final_payload)

    except Exception as e:
        log.error(f"任務 {task_id} 執行期間發生未預期的嚴重錯誤: {e}", exc_info=True)
        error_payload = {"error": f"伺服器內部錯誤: {str(e)}"}
        db_client.update_task_status(task_id, 'failed', json.dumps(error_payload))
        await broadcast_status(task_id, url, "failed", message=error_payload["error"])

# --- API 路由 (更新) ---
@router.post("/download", response_model=List[TaskResponse], status_code=202)
async def start_multiple_downloads(req: DownloadRequest):
    if not req.urls:
        raise HTTPException(status_code=400, detail="URL 列表不可為空。")

    tasks_created = []
    for url in req.urls:
        if not url.strip() or not (url.startswith("http://") or url.startswith("https://")):
            continue

        task_id = str(uuid.uuid4())

        # 建立初始 payload
        initial_payload = {
            "url": url.strip(),
            "download_type": req.download_type,
            "audio_format": req.audio_format,
            "video_resolution": req.video_resolution
        }
        # 在資料庫中建立任務紀錄
        db_client.add_task(task_id, json.dumps(initial_payload), 'audio_download', 'starting')

        # 啟動背景任務
        asyncio.create_task(run_download_task(
            task_id, url.strip(), req.download_type, req.audio_format, req.video_resolution
        ))

        tasks_created.append(TaskResponse(
            task_id=task_id,
            url=url,
            message=f"已成功為 URL '{url[:70]}...' 建立下載任務。"
        ))

    if not tasks_created:
         raise HTTPException(status_code=400, detail="未提供任何有效的 URL。")

    return tasks_created

@router.get("/tasks", status_code=200)
async def get_all_download_tasks():
    """
    獲取所有音訊下載任務的歷史紀錄。
    """
    try:
        # 獲取所有任務，然後在記憶體中過濾
        all_tasks = db_client.get_all_tasks()
        tasks = [task for task in all_tasks if task.get("task_type") == 'audio_download']

        # 為了前端方便處理，我們對 payload 和 result 進行解析
        for task in tasks:
            try:
                if task.get("payload"):
                    task["payload"] = json.loads(task["payload"])
                if task.get("result"):
                    task["result"] = json.loads(task["result"])
            except (json.JSONDecodeError, TypeError):
                # 如果解析失敗，保持原樣或設定為 None
                log.warning(f"無法解析任務 {task.get('task_id')} 的 JSON 欄位。")
                task["result"] = {}

        return tasks
    except Exception as e:
        log.error(f"獲取音訊下載任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法從資料庫獲取任務列表。")