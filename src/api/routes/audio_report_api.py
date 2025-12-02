# -*- coding: utf-8 -*-
import asyncio
import logging
import sqlite3
from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
import json
from pathlib import Path
import sys
import subprocess
from datetime import datetime

from src.db import database
from src.core import key_manager
from src.api.dependencies import get_db

log = logging.getLogger("audio_report_api")
router = APIRouter(prefix="/api/audio_report", tags=["Audio Report"])

class DownloadRequest(BaseModel):
    urls: List[str] = Field(..., description="要下載的 URL 列表。")
    download_type: str = Field("audio", description="下載類型：'audio' 或 'video'。")
    audio_format: Optional[str] = Field("m4a", description="音訊格式，例如 'm4a', 'mp3'。")
    video_resolution: Optional[str] = Field("best", description="影片解析度，例如 '1080p', '720p'。")

class TaskResponse(BaseModel):
    task_id: str
    url: str
    message: str

AUDIO_DIR = Path("downloads/audio")
VIDEO_DIR = Path("downloads/video")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

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

async def run_download_task(task_id: str, url: str, download_type: str, audio_format: str, video_resolution: str):
    log.info(f"任務 {task_id}: 開始處理 URL: {url} (類型: {download_type})")
    await broadcast_status(task_id, url, "starting", message=f"已建立任務，準備下載 {download_type}...")
    db_conn = database.get_db_connection()
    try:
        with db_conn:
            database.update_task_status(db_conn, task_id, "processing", json.dumps({"message": "Download starting"}))
        output_dir = VIDEO_DIR if download_type == "video" else AUDIO_DIR
        command = [sys.executable, "-u", "src/tools/youtube_downloader.py", "--url", url, "--output-dir", str(output_dir), "--download-type", download_type, "--audio-format", audio_format, "--video-resolution", video_resolution]
        log.info(f"任務 {task_id}: 執行指令: {' '.join(command)}")
        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()
        with db_conn:
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
                database.update_task_status(db_conn, task_id, "failed", json.dumps({"error": error_message, "code": error_code}))
                await broadcast_status(task_id, url, "failed", message=error_message, error_code=error_code)
                return
            result = json.loads(stdout.decode('utf-8'))
            log.info(f"任務 {task_id} 成功完成。結果: {result}")
            output_path = Path(result["output_path"])
            preview_url = f"/downloads/{download_type}/{output_path.name}"
            video_title = result.get("video_title", "未命名任務")
            final_result = {"message": f"檔案 '{video_title}' 下載成功。", "filename": output_path.name, "video_title": video_title, "output_path": str(output_path), "preview_url": preview_url}
            database.update_task_status(db_conn, task_id, "completed", json.dumps(final_result))
            database.update_task(db_conn, task_id, {"task_name": video_title})
            await broadcast_status(task_id, url, "completed", **final_result)
    except Exception as e:
        log.error(f"任務 {task_id} 執行期間發生未預期的嚴重錯誤: {e}", exc_info=True)
        error_message = f"伺服器內部錯誤: {str(e)}"
        if db_conn:
            with db_conn:
                database.update_task_status(db_conn, task_id, "failed", json.dumps({"error": error_message}))
        await broadcast_status(task_id, url, "failed", message=error_message)
    finally:
        if db_conn:
            db_conn.close()

@router.post("/download", response_model=List[TaskResponse], status_code=202)
async def start_multiple_downloads(req: DownloadRequest, db: sqlite3.Connection = Depends(get_db)):
    if not req.urls:
        raise HTTPException(status_code=400, detail="URL 列表不可為空。")
    tasks_created = []
    with db:
        for url in req.urls:
            url = url.strip()
            if not url or not (url.startswith("http://") or url.startswith("https://")):
                continue
            task_id = str(uuid.uuid4())
            payload = {"url": url, "download_type": req.download_type, "audio_format": req.audio_format, "video_resolution": req.video_resolution}
            database.add_task(db, task_id=task_id, payload=json.dumps(payload), task_type="audio_download", task_name=url)
            asyncio.create_task(run_download_task(task_id, url, req.download_type, req.audio_format, req.video_resolution))
            tasks_created.append(TaskResponse(task_id=task_id, url=url, message=f"已成功為 URL '{url[:70]}...' 建立下載任務。"))
    if not tasks_created:
        raise HTTPException(status_code=400, detail="未提供任何有效的 URL。")
    return tasks_created

@router.get("/tasks", status_code=200)
async def get_all_download_tasks(db: sqlite3.Connection = Depends(get_db)):
    try:
        tasks = database.get_all_tasks(db, task_type="audio_download")
        return tasks
    except Exception as e:
        log.error(f"獲取音訊下載任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法從資料庫讀取任務紀錄。")

@router.get("/completed_downloads", status_code=200)
async def get_completed_downloads(db: sqlite3.Connection = Depends(get_db)):
    try:
        all_tasks = database.get_all_tasks(db, task_type="audio_download")
        completed_files = []
        for task in all_tasks:
            if task.get('status') == 'completed' and task.get('result'):
                try:
                    result_data = json.loads(task['result'])
                    if result_data.get('output_path') and result_data['output_path'].startswith(str(AUDIO_DIR)):
                        completed_files.append({"filename": result_data.get("filename", "未知檔案"), "path": result_data.get("output_path"), "title": result_data.get("video_title", task.get("task_name"))})
                except (json.JSONDecodeError, KeyError):
                    continue
        return completed_files
    except Exception as e:
        log.error(f"獲取已完成下載時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法讀取已完成的下載紀錄。")

class AnalysisRequest(BaseModel):
    file_path: str = Field(..., description="要分析的音訊檔案的完整路徑。")
    model: str = Field(..., description="要使用的 Gemini 模型。")
    tasks: List[str] = Field(..., description="要執行的任務列表，例如 ['transcript', 'summary']。")
    api_key: Optional[str] = Field(None, description="使用者提供的臨時 API 金鑰。")

async def run_analysis_task(task_id: str, file_path: str, model: str, tasks: list, api_key: str):
    log.info(f"分析任務 {task_id}: 開始處理檔案 {file_path}")
    await manager.broadcast(json.dumps({"type": "ANALYSIS_STATUS", "payload": {"task_id": task_id, "status": "starting", "message": "分析任務已建立，正在呼叫 AI 模型..."}}))
    db_conn = database.get_db_connection()
    try:
        with db_conn:
            database.update_task_status(db_conn, task_id, "processing", json.dumps({"message": "Calling AI model..."}))
        command = [sys.executable, "-u", "src/tools/audio_analyzer.py", "--file-path", file_path, "--model", model, "--tasks", ",".join(tasks), "--api-key", api_key]
        log.info(f"分析任務 {task_id}: 執行指令: {' '.join(command)}")
        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()
        with db_conn:
            if process.returncode != 0:
                error_message = stderr.decode('utf-8', errors='ignore').strip()
                log.error(f"分析任務 {task_id} 失敗。返回碼: {process.returncode}。錯誤: {error_message}")
                database.update_task_status(db_conn, task_id, "failed", json.dumps({"error": error_message}))
                await manager.broadcast(json.dumps({"type": "ANALYSIS_STATUS", "payload": {"task_id": task_id, "status": "failed", "message": error_message}}))
                return
            result = json.loads(stdout.decode('utf-8'))
            log.info(f"分析任務 {task_id} 成功完成。")
            database.update_task_status(db_conn, task_id, "completed", json.dumps(result))
            await manager.broadcast(json.dumps({"type": "ANALYSIS_STATUS", "payload": {"task_id": task_id, "status": "completed", "message": "分析完成", "result": result}}))
    except Exception as e:
        log.error(f"分析任務 {task_id} 執行期間發生未預期的嚴重錯誤: {e}", exc_info=True)
        error_message = f"伺服器內部錯誤: {str(e)}"
        if db_conn:
            with db_conn:
                database.update_task_status(db_conn, task_id, "failed", json.dumps({"error": error_message}))
        await manager.broadcast(json.dumps({"type": "ANALYSIS_STATUS", "payload": {"task_id": task_id, "status": "failed", "message": error_message}}))
    finally:
        if db_conn:
            db_conn.close()

@router.post("/analyze", status_code=202)
async def start_analysis(req: AnalysisRequest, db: sqlite3.Connection = Depends(get_db)):
    if not Path(req.file_path).exists():
        raise HTTPException(status_code=404, detail=f"檔案不存在: {req.file_path}")
    api_key = req.api_key
    if not api_key:
        log.info("前端未提供 API 金鑰，正在嘗試從後端金鑰池獲取...")
        with db:
            api_key = key_manager.get_key_by_type(db, "gemini")
        if not api_key:
            log.error("金鑰池中沒有可用的 Gemini API 金鑰。")
            raise HTTPException(status_code=400, detail="系統金鑰池中沒有可用的 Gemini API 金鑰，請先新增或驗證您的金鑰。")
        log.info("成功從金鑰池中獲取一個有效的 Gemini 金鑰。")
    task_id = str(uuid.uuid4())
    task_name = f"分析任務 for {Path(req.file_path).name}"
    with db:
        database.add_task(db, task_id=task_id, payload=json.dumps(req.model_dump()), task_type="audio_analysis", task_name=task_name)
    asyncio.create_task(run_analysis_task(task_id, req.file_path, req.model, req.tasks, api_key))
    return {"task_id": task_id, "message": f"已成功建立分析任務: {task_name}"}

@router.get("/reports", status_code=200)
async def get_detailed_analysis_reports(db: sqlite3.Connection = Depends(get_db)):
    try:
        tasks = database.get_all_tasks(db, task_type="audio_analysis")
        detailed_reports = []
        for task in tasks:
            if task.get('status') != 'completed':
                continue
            try:
                payload = json.loads(task.get('payload', '{}'))
                result = json.loads(task.get('result', '{}'))
                PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
                def to_web_path(local_path_str):
                    if not local_path_str: return None
                    try:
                        abs_path = Path(local_path_str)
                        relative_path = abs_path.relative_to(PROJECT_ROOT)
                        return relative_path.as_posix()
                    except (ValueError, TypeError):
                        log.warning(f"無法將路徑 '{local_path_str}' 轉換為相對於專案根目錄 '{PROJECT_ROOT}' 的 Web 路徑。")
                        return None
                report_card_data = {"taskId": task.get('task_id'), "reportTitle": task.get('task_name', '未命名報告'), "sourceFilename": Path(payload.get('file_path', '未知來源')).name, "modelUsed": payload.get('model', '未知模型'), "processingTime": result.get('processing_time_seconds', 0), "totalTokens": result.get('total_tokens', 0), "creationDate": task.get('created_at'), "outputFiles": []}
                for file_info in result.get('output_files', []):
                    local_path = file_info.get('path')
                    web_path = to_web_path(local_path)
                    if not (local_path and Path(local_path).exists() and web_path):
                        log.warning(f"已跳過不存在或路徑無效的檔案: {local_path}")
                        continue
                    file_stat = Path(local_path).stat()
                    report_card_data['outputFiles'].append({"type": file_info.get('type', '檔案'), "name": Path(local_path).name, "path": web_path, "size": file_stat.st_size, "modifiedTime": datetime.fromtimestamp(file_stat.st_mtime).isoformat()})
                if report_card_data['outputFiles']:
                    detailed_reports.append(report_card_data)
            except (json.JSONDecodeError, KeyError) as e:
                log.warning(f"處理任務 {task.get('task_id')} 時發生資料解析錯誤: {e}")
                continue
        detailed_reports.sort(key=lambda x: x['creationDate'], reverse=True)
        return {"reports": detailed_reports}
    except Exception as e:
        log.error(f"獲取詳細分析報告時發生嚴重錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法從資料庫讀取報告紀錄。")
