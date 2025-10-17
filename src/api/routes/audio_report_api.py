# -*- coding: utf-8 -*-
import asyncio
import logging
from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from typing import List
import uuid
import json
from pathlib import Path
import sys
import subprocess

# --- 專案模組導入 ---
# 這裡我們不直接導入，而是透過 subprocess 呼叫，以確保環境隔離和可靠性

# --- 日誌設定 ---
log = logging.getLogger("audio_report_api")

# --- FastAPI 路由器 ---
router = APIRouter(prefix="/api/audio_report", tags=["Audio Report"])

# --- 資料模型 ---
class DownloadRequest(BaseModel):
    urls: List[str] = Field(..., description="要下載的 URL 列表。")

class TaskResponse(BaseModel):
    task_id: str
    url: str
    message: str

# --- 靜態路徑設定 ---
DOWNLOADS_DIR = Path("downloads/audio")
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

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
        # 使用 asyncio.gather 來並行發送訊息
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
    """廣播任務狀態給所有連接的 WebSocket 客戶端。"""
    payload = {
        "task_id": task_id,
        "url": url,
        "status": status,
        **kwargs
    }
    message_json = json.dumps({"type": "DOWNLOAD_STATUS", "payload": payload})
    await manager.broadcast(message_json)

# --- 背景任務 ---
async def run_download_task(task_id: str, url: str):
    """在背景使用 subprocess 執行 youtube_downloader.py 腳本。"""
    log.info(f"任務 {task_id}: 開始處理 URL: {url}")
    await broadcast_status(task_id, url, "starting", message="已建立任務，正準備下載...")

    try:
        command = [
            sys.executable,
            "-u",  # Unbuffered output
            "src/tools/youtube_downloader.py",
            "--url", url,
            "--output-dir", str(DOWNLOADS_DIR),
            "--download-type", "audio"
        ]

        log.info(f"任務 {task_id}: 執行指令: {' '.join(command)}")

        # 使用 asyncio.create_subprocess_exec 來非阻塞地執行子進程
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # 監控 stderr 來獲取進度更新
        # (這裡假設 youtube_downloader.py 會將進度打印到 stderr)
        # 為了簡單起見，我們在這裡只處理最終結果

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_message = stderr.decode('utf-8').strip()
            log.error(f"任務 {task_id} 失敗。返回碼: {process.returncode}。錯誤: {error_message}")
            await broadcast_status(task_id, url, "failed", message=error_message)
            return

        # 解析 stdout 以獲取 JSON 結果
        try:
            result = json.loads(stdout.decode('utf-8'))
            log.info(f"任務 {task_id} 成功完成。結果: {result}")
            await broadcast_status(
                task_id,
                url,
                "completed",
                message=f"檔案 '{result.get('video_title', 'N/A')}' 下載成功。",
                filename=Path(result["output_path"]).name,
                video_title=result.get("video_title"),
                output_path=result["output_path"]
            )
        except (json.JSONDecodeError, KeyError) as e:
            log.error(f"任務 {task_id}: 無法解析來自 youtube_downloader.py 的 JSON 輸出: {e}")
            await broadcast_status(task_id, url, "failed", message="無法解析下載工具的輸出。")

    except Exception as e:
        log.error(f"任務 {task_id} 執行期間發生未預期的嚴重錯誤: {e}", exc_info=True)
        await broadcast_status(task_id, url, "failed", message=f"伺服器內部錯誤: {str(e)}")


# --- API 路由 ---
@router.post("/download", response_model=List[TaskResponse], status_code=202)
async def start_multiple_downloads(req: DownloadRequest, request: Request):
    """
    接收多個 URL，為每個 URL 創建一個獨立的背景下載任務。
    """
    if not req.urls:
        raise HTTPException(status_code=400, detail="URL 列表不可為空。")

    tasks_created = []
    for url in req.urls:
        if not url.strip() or not (url.startswith("http://") or url.startswith("https://")):
            continue

        task_id = str(uuid.uuid4())

        # FastAPI 的 BackgroundTasks 適用於同步函式，但我們的 run_download_task 是異步的。
        # 對於異步背景任務，最好使用 asyncio.create_task
        asyncio.create_task(run_download_task(task_id, url.strip()))

        tasks_created.append(TaskResponse(
            task_id=task_id,
            url=url,
            message=f"已成功為 URL '{url[:70]}...' 建立下載任務。"
        ))

    if not tasks_created:
         raise HTTPException(status_code=400, detail="未提供任何有效的 URL。")

    return tasks_created