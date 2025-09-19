import logging
import sys
from pathlib import Path
import json
import asyncio
import functools

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends

# V4 優化：移除 get_db_connection，全面改用依賴注入
# from db.database import get_db_connection
from db.client import DBClient
from ..dependencies import get_db


# --- 常數與設定 ---
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()


# --- API 端點 ---
@router.get("/pending_urls")
async def get_pending_urls(db: DBClient = Depends(get_db)):
    """
    (V4 優化後) 獲取所有狀態為 'pending' 的網址列表。
    """
    log.info("API: 收到獲取待處理網址列表的請求。")
    try:
        rows = db.get_urls_by_statuses(statuses=['pending'])
        results = [
            {
                "id": row['id'],
                "url": row['url'],
                "author": row['author'],
                "message_date": row['message_date'],
                "message_time": row['message_time'],
                "title": row['title'] # Jules @ 2025-09-17: 修正 API，將 title 欄位加入回傳的 JSON 中
            }
            for row in rows
        ]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API: 獲取待處理網址時發生錯誤: {e}", exc_info=True)
        # 假設 DBClient 在出錯時會引發一個可捕獲的異常
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail="獲取待處理網址時發生伺服器內部錯誤。")


@router.get("/completed")
async def get_completed_downloads(db: DBClient = Depends(get_db)):
    """
    (V4 優化後) 獲取所有狀態為 'completed' (已下載完成) 的檔案列表。
    """
    log.info("API: 收到獲取已完成下載列表的請求。")
    try:
        rows = db.get_urls_by_statuses(statuses=['completed'])
        # 從 local_path 提取檔名，並確保 local_path 存在
        results = [
            {
                "id": row['id'],
                "url": row['url'],
                "filename": Path(row['local_path']).name,
                "completed_at": row['created_at']
            }
            for row in rows if row['local_path']
        ]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API: 獲取已完成下載列表時發生錯誤: {e}", exc_info=True)
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail="獲取已完成下載列表時發生伺服器內部錯誤。")


# --- Pydantic 模型 ---
class DownloadRequest(BaseModel):
    ids: List[int]

import uuid
import datetime
import redis

# --- V7 微服務重構 ---

REDIS_HOST = "localhost"
REDIS_PORT = 6379
DOWNLOAD_COMPLETE_CHANNEL = "tasks:download_complete"

def publish_download_complete(task_id: str, status: str, file_path: str, original_filename: str):
    """
    將下載完成的訊息發布到 Redis。
    """
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

    payload = {
        "file_path": file_path,
        "original_filename": original_filename,
    }

    message = {
        "task_id": task_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_service": "downloader_service",
        "status": "success" if status == "download_complete" else "failure",
        "payload": payload
    }

    try:
        redis_client.publish(DOWNLOAD_COMPLETE_CHANNEL, json.dumps(message))
        log.info(f"[Downloader] 已將任務 {task_id} 的下載完成訊息發布至頻道 '{DOWNLOAD_COMPLETE_CHANNEL}'")
    except Exception as e:
        log.error(f"[Downloader] 發布訊息至 Redis 時失敗: {e}", exc_info=True)


def _run_download_blocking_task(task_id: str, db_client: DBClient, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """
    (V7 重構後) 執行單一檔案下載的同步阻塞部分。
    現在由 task_id 驅動，並在成功後發布 Redis 訊息。
    """
    log.info(f"背景任務：開始處理下載任務 ID: {task_id}")
    final_status = 'download_failed'

    try:
        task_record = db_client.get_task_status(task_id)
        if not task_record:
            raise ValueError(f"在資料庫中找不到任務 ID 為 {task_id} 的任務。")

        payload = json.loads(task_record['payload'])
        url_to_download = payload['url']
        original_filename_from_title = payload.get('title', 'untitled')

        log.info(f"背景任務：準備從 {url_to_download} 下載 (任務 ID: {task_id})...")

        from tools.universal_downloader import download_file # 使用通用下載器
        download_dir = SRC_DIR.parent / "downloads"

        # Universal downloader 返回 (檔案路徑, 原始檔名) 或 (None, None)
        downloaded_path, original_filename = download_file(
            url=url_to_download,
            output_dir=str(download_dir)
        )

        if downloaded_path:
            final_status = 'download_complete'
            result_payload = {"local_path": downloaded_path, "original_filename": original_filename}
            db_client.update_task_status(task_id, final_status, result_payload)
            log.info(f"背景任務：任務 {task_id} 下載成功，路徑: {downloaded_path}")

            # 發射信號彈！
            publish_download_complete(task_id, final_status, downloaded_path, original_filename)
        else:
            raise Exception("通用下載器未能成功下載檔案。")

    except Exception as e:
        error_message = f"處理下載任務 {task_id} 時發生嚴重錯誤: {e}"
        log.error(error_message, exc_info=True)
        db_client.update_task_status(task_id, 'download_failed', {"error": error_message})
    finally:
        # WebSocket 通知仍然保留，以便 UI 即時更新
        final_record = db_client.get_task_status(task_id)
        notification_msg = {
            "type": "task_update",
            "task_type": "download",
            "task_id": str(task_id),
            "status": final_status,
            "result": final_record
        }
        asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)
        log.info(f"背景任務：已為任務 ID {task_id} 發送完成通知至佇列。")


async def run_task_wrapper(task_id: str, semaphore: asyncio.Semaphore, blocking_func, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, **kwargs):
    """
    (V7 修改) 通用非同步包裝函式，現在使用字串類型的 task_id。
    """
    async with semaphore:
        log.info(f"任務 {task_id} 已取得信號量，準備執行...")
        try:
            # 修改了這裡，傳遞 task_id 而不是 url_id
            partial_func = functools.partial(blocking_func, task_id=task_id, queue=queue, loop=loop, **kwargs)
            await loop.run_in_executor(None, partial_func)
        except Exception as e:
            log.error(f"包裝函式捕獲到未預期的錯誤 (任務 {task_id}): {e}", exc_info=True)
        finally:
            log.info(f"任務 {task_id} 執行完畢，釋放信號量。")


@router.post("/start_downloads")
async def start_downloads(
    payload: DownloadRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: DBClient = Depends(get_db)
):
    """
    (V7 重構後) 接收 URL ID 列表，為每個 ID 建立一個新的、獨立的任務，
    並使用新的 task_id 啟動背景下載。
    """
    url_ids = payload.ids
    if not url_ids:
        raise HTTPException(status_code=400, detail="未提供要下載的 URL ID。")

    log.info(f"API: 收到 {len(url_ids)} 個項目的下載請求。")

    semaphore = request.app.state.download_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()

    if not semaphore or not queue:
        raise HTTPException(status_code=500, detail="伺服器狀態未完全初始化（缺少佇列或信號量）。")

    created_tasks_count = 0
    for url_id in url_ids:
        url_record = db.get_url_by_id(url_id)
        if not url_record:
            log.warning(f"找不到 URL ID: {url_id}，已跳過。")
            continue

        # 為每個下載請求建立一個新的、唯一的任務
        task_id = str(uuid.uuid4())
        task_payload = {
            "url": url_record['url'],
            "author": url_record['author'],
            "message_date": url_record['message_date'],
            "message_time": url_record['message_time'],
            "title": url_record['title'],
            "original_url_id": url_id # 保留原始關聯
        }

        # 在資料庫中建立新任務
        db.add_task(task_id, json.dumps(task_payload), task_type='download', status='pending')
        log.info(f"已為 URL ID {url_id} 建立新任務，任務 ID: {task_id}")

        # 使用新的 task_id 啟動背景任務
        background_tasks.add_task(
            run_task_wrapper,
            task_id=task_id,
            semaphore=semaphore,
            blocking_func=_run_download_blocking_task,
            queue=queue,
            loop=loop,
            db_client=db
        )
        created_tasks_count += 1

    return JSONResponse(
        content={"message": f"已成功為 {created_tasks_count} 個項目建立背景下載任務。"}
    )
