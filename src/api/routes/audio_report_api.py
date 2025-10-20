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
from src.db import database as db

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
# 根據下載類型，建立不同的子目錄
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

    try:
        # 根據類型決定輸出目錄
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
            stdout_str = stdout.decode('utf-8', errors='ignore').strip()
            stderr_str = stderr.decode('utf-8', errors='ignore').strip()
            error_message = stderr_str
            error_code = "GENERAL_ERROR"

            if stdout_str:
                try:
                    error_json = json.loads(stdout_str)
                    error_message = error_json.get("error", error_message)
                    error_code = error_json.get("error_code", error_code)
                except json.JSONDecodeError:
                    log.warning(f"任務 {task_id} 的 stdout 不是有效的 JSON，將使用 stderr 作為錯誤訊息。")

            log.error(f"任務 {task_id} 失敗。返回碼: {process.returncode}。錯誤: {error_message}")
            db.update_task_status(task_id, "failed", json.dumps({"error": error_message, "error_code": error_code}))
            await broadcast_status(task_id, url, "failed", message=error_message, error_code=error_code)
            return

        result = json.loads(stdout.decode('utf-8'))
        log.info(f"任務 {task_id} 成功完成。結果: {result}")

        output_path = Path(result["output_path"])
        preview_url = f"/downloads/{download_type}/{output_path.name}"

        # 將成功的結果更新回資料庫
        db.update_task_status(task_id, "completed", json.dumps(result))

        await broadcast_status(
            task_id, url, "completed",
            message=f"檔案 '{result.get('video_title', 'N/A')}' 下載成功。",
            filename=output_path.name,
            video_title=result.get("video_title"),
            output_path=str(output_path),
            preview_url=preview_url
        )
    except Exception as e:
        log.error(f"任務 {task_id} 執行期間發生未預期的嚴重錯誤: {e}", exc_info=True)
        db.update_task_status(task_id, "failed", json.dumps({"error": f"伺服器內部錯誤: {str(e)}"}))
        await broadcast_status(task_id, url, "failed", message=f"伺服器內部錯誤: {str(e)}")

# --- API 路由 (更新) ---
@router.get("/history", status_code=200)
async def get_download_history():
    """
    獲取 'audio_report' 類型的下載任務歷史紀錄。
    """
    try:
        history_tasks = db.get_tasks_by_type("audio_report")
        return history_tasks
    except Exception as e:
        log.error(f"獲取下載歷史紀錄時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法獲取歷史紀錄。")

@router.post("/download", response_model=List[TaskResponse], status_code=202)
async def start_multiple_downloads(req: DownloadRequest):
    if not req.urls:
        raise HTTPException(status_code=400, detail="URL 列表不可為空。")

    tasks_created = []
    for url in req.urls:
        if not url.strip() or not (url.startswith("http://") or url.startswith("https://")):
            continue

        task_id = str(uuid.uuid4())

        # 在啟動背景任務前，先將任務新增到資料庫
        payload = {"url": url.strip(), "download_type": req.download_type}
        db.add_task(task_id, json.dumps(payload), task_type="audio_report")

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