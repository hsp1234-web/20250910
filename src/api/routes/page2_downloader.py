import logging
import sys
from pathlib import Path
import json
import asyncio
import functools

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Any

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

# V78 重構：不再有 DBClient，直接使用 get_db 注入的 database 模組
from ..dependencies import get_db

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()

# --- API 端點 ---
@router.get("/pending_urls")
async def get_pending_urls(db: Any = Depends(get_db)):
    """
    獲取所有狀態為 'pending' 的網址列表。
    """
    log.info("API: 收到獲取待處理網址列表的請求。")
    try:
        # 'db' 現在是 database 模組的別名
        rows = db.get_urls_by_statuses(statuses=['pending'])
        results = [{"id": row['id'], "url": row['url'], "author": row['author'], "message_date": row['message_date'], "message_time": row['message_time'], "title": row.get('title')} for row in rows]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API: 獲取待處理網址時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取待處理網址時發生伺服器內部錯誤。")

@router.get("/completed")
async def get_completed_downloads(db: Any = Depends(get_db)):
    """
    獲取所有狀態為 'completed' (已下載完成) 的檔案列表。
    """
    log.info("API: 收到獲取已完成下載列表的請求。")
    try:
        rows = db.get_urls_by_statuses(statuses=['completed'])
        results = [{"id": row['id'], "url": row['url'], "filename": Path(row['local_path']).name, "completed_at": row['created_at']} for row in rows if row.get('local_path')]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API: 獲取已完成下載列表時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取已完成下載列表時發生伺服器內部錯誤。")

class DownloadRequest(BaseModel):
    ids: List[int]

def _run_download_blocking_task(url_id: int, db, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    log.info(f"背景任務：開始處理下載 URL ID: {url_id}")
    try:
        url_record = db.get_url_by_id(url_id)
        if not url_record: raise ValueError(f"找不到 ID 為 {url_id} 的 URL。")

        from tools.drive_downloader import download_file
        download_dir = SRC_DIR.parent / "downloads"
        downloaded_path = download_file(url=url_record['url'], output_dir=str(download_dir), url_id=url_id, author=url_record['author'], message_date=url_record['message_date'], message_time=url_record['message_time'])

        if downloaded_path:
            db.update_url(url_id, {"status": 'completed', "local_path": downloaded_path, "status_message": '下載成功'})
        else:
            db.update_url(url_id, {"status": 'download_failed', "status_message": '下載失敗'})
    except Exception as e:
        log.error(f"背景任務處理 URL ID {url_id} 時發生錯誤: {e}", exc_info=True)
        db.update_url(url_id, {"status": 'failed', "status_message": f"發生未預期錯誤: {e}"})
    finally:
        final_record = db.get_url_by_id(url_id)
        notification_msg = {"type": "task_update", "task_type": "download", "task_id": str(url_id), "status": final_record['status'], "result": final_record}
        asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)

async def run_task_wrapper(task_id: int, semaphore: asyncio.Semaphore, blocking_func, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, **kwargs):
    async with semaphore:
        log.info(f"任務 {task_id} 取得信號量，準備執行...")
        try:
            await loop.run_in_executor(None, functools.partial(blocking_func, url_id=task_id, queue=queue, loop=loop, **kwargs))
        finally:
            log.info(f"任務 {task_id} 執行完畢，釋放信號量。")

@router.post("/start_downloads")
async def start_downloads(payload: DownloadRequest, background_tasks: BackgroundTasks, request: Request, db: Any = Depends(get_db)):
    url_ids = payload.ids
    if not url_ids: raise HTTPException(status_code=400, detail="未提供要下載的 URL ID。")
    log.info(f"API: 收到 {len(url_ids)} 個項目的下載請求。")

    semaphore = request.app.state.download_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()

    try:
        for url_id in url_ids:
            db.update_url(url_id, {"status": "downloading", "status_message": "已加入下載佇列"})
            background_tasks.add_task(run_task_wrapper, task_id=url_id, semaphore=semaphore, blocking_func=_run_download_blocking_task, queue=queue, loop=loop, db=db)
        return JSONResponse(content={"message": f"已成功為 {len(url_ids)} 個項目建立背景下載任務。"})
    except Exception as e:
        log.error(f"API: 啟動下載任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="啟動下載任務時發生伺服器內部錯誤。")
