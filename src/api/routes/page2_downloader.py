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

from db.database import get_db_connection
from db.client import get_client

# --- 常數與設定 ---
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()
DB_CLIENT = get_client()

# --- API 端點 ---
@router.get("/pending_urls")
async def get_pending_urls():
    """
    獲取所有狀態為 'pending' 的網址列表。
    現在也會獲取作者和訊息時間等欄位，以便在前端表格中顯示。
    """
    log.info("API: 收到獲取待處理網址列表的請求。")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, url, author, message_date, message_time FROM extracted_urls WHERE status = 'pending' ORDER BY created_at DESC"
        )
        rows = cursor.fetchall()
        results = [
            {
                "id": row['id'],
                "url": row['url'],
                "author": row['author'],
                "message_date": row['message_date'],
                "message_time": row['message_time'],
            }
            for row in rows
        ]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API: 獲取待處理網址時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取待處理網址時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()


@router.get("/completed")
async def get_completed_downloads():
    """
    獲取所有狀態為 'completed' (已下載完成) 的檔案列表。
    這是為了在頁面二顯示已完成的項目。
    """
    log.info("API: 收到獲取已完成下載列表的請求。")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, url, local_path, created_at FROM extracted_urls WHERE status = 'completed' ORDER BY created_at DESC")
        rows = cursor.fetchall()
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
        raise HTTPException(status_code=500, detail="獲取已完成下載列表時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()


# --- Pydantic 模型 ---
class DownloadRequest(BaseModel):
    ids: List[int]

# --- 背景任務函式 (重構後) ---

def _run_download_blocking_task(url_id: int, db_client, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """
    執行單一檔案下載的同步阻塞部分。
    現在透過 queue 和 loop 來發送非同步通知。
    """
    log.info(f"背景任務：開始處理下載 URL ID: {url_id}")
    final_status = 'failed' # 預設為失敗
    status_message = ''
    result_payload = {}

    try:
        # 步驟 1: 獲取所有命名所需的資訊
        url_record = db_client.get_url_by_id(url_id)
        if not url_record:
            raise ValueError(f"在資料庫中找不到 ID 為 {url_id} 的 URL。")

        url_to_download = url_record['url']
        author = url_record['author']
        message_date = url_record['message_date']
        message_time = url_record['message_time']
        log.info(f"背景任務：準備從 {url_to_download} 下載 (ID: {url_id})...")

        # 步驟 2: 執行智慧化下載
        from tools.drive_downloader import download_file
        download_dir = SRC_DIR.parent / "downloads"

        downloaded_path = download_file(
            url=url_to_download,
            output_dir=str(download_dir),
            url_id=url_id,
            author=author,
            message_date=message_date,
            message_time=message_time
        )

        # 步驟 3: 根據下載結果更新資料庫
        if downloaded_path:
            final_status = 'completed'
            status_message = '下載成功'
            result_payload = {"local_path": downloaded_path}
            db_client.update_url(url_id, {"status": final_status, "local_path": downloaded_path, "status_message": status_message})
            log.info(f"背景任務：URL ID {url_id} 下載成功，路徑: {downloaded_path}")
        else:
            final_status = 'download_failed'
            status_message = '下載失敗，請檢查日誌'
            result_payload = {"error": status_message}
            db_client.update_url(url_id, {"status": final_status, "status_message": status_message})
            log.error(f"背景任務：URL ID {url_id} 下載失敗。")

    except Exception as e:
        log.error(f"背景任務：處理 URL ID {url_id} 時發生嚴重錯誤: {e}", exc_info=True)
        final_status = 'failed'
        status_message = f"發生未預期錯誤: {e}"
        result_payload = {"error": str(e)}
        db_client.update_url(url_id, {"status": final_status, "status_message": status_message})
    finally:
        # 步驟 4: 無論成功或失敗，都將通知放入佇列
        # 確保我們有最新的資料
        final_record = db_client.get_url_by_id(url_id)
        notification_msg = {
            "type": "task_update",
            "task_type": "download",
            "task_id": str(url_id),
            "status": final_status,
            "result": final_record # 回傳整個紀錄，讓前端可以更新所有欄位
        }
        asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)
        log.info(f"背景任務：已為 URL ID {url_id} 發送完成通知至佇列。")


async def run_task_wrapper(task_id: int, semaphore: asyncio.Semaphore, blocking_func, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, **kwargs):
    """
    一個通用的非同步包裝函式，用於控制併發並執行阻塞的任務。
    """
    async with semaphore:
        log.info(f"任務 {task_id} 已取得信號量，準備執行...")
        try:
            partial_func = functools.partial(blocking_func, url_id=task_id, queue=queue, loop=loop, **kwargs)
            await loop.run_in_executor(None, partial_func)
        except Exception as e:
            log.error(f"包裝函式捕獲到未預期的錯誤 (任務 {task_id}): {e}", exc_info=True)
        finally:
            log.info(f"任務 {task_id} 執行完畢，釋放信號量。")


@router.post("/start_downloads")
async def start_downloads(payload: DownloadRequest, background_tasks: BackgroundTasks, request: Request):
    """
    (重構後) 接收要下載的 URL ID 列表，並為每一個 ID 建立一個使用佇列通知的背景下載任務。
    """
    url_ids = payload.ids
    if not url_ids:
        raise HTTPException(status_code=400, detail="未提供要下載的 URL ID。")

    log.info(f"API: 收到 {len(url_ids)} 個項目的下載請求。")

    # 從 app.state 獲取佇列和信號量
    semaphore = request.app.state.download_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()

    if not semaphore or not queue:
        raise HTTPException(status_code=500, detail="伺服器狀態未完全初始化（缺少佇列或信號量）。")

    try:
        # 立即將所有請求的 URL 狀態更新為 'downloading'
        # JULES (2025-09-14): 修正錯誤。DBClient 沒有 execute_query 方法。
        # 改為使用迴圈和高階的 update_url 方法，以符合現有的抽象層設計。
        for url_id in url_ids:
            DB_CLIENT.update_url(url_id, {"status": "downloading", "status_message": "已加入下載佇列"})
        log.info(f"API: 已將 {len(url_ids)} 個 URL 的狀態更新為 'downloading'。")

        # 為每個 URL 新增一個背景任務
        for url_id in url_ids:
            background_tasks.add_task(
                run_task_wrapper,
                task_id=url_id,
                semaphore=semaphore,
                blocking_func=_run_download_blocking_task,
                queue=queue,
                loop=loop,
                db_client=DB_CLIENT  # 傳遞 client 進去
            )

        return JSONResponse(
            content={"message": f"已成功為 {len(url_ids)} 個項目建立背景下載任務。"}
        )
    except Exception as e:
        log.error(f"API: 啟動下載任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="啟動下載任務時發生伺服器內部錯誤。")
