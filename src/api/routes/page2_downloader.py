import logging
import sys
from pathlib import Path
import json
import asyncio
import functools
import requests

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from db.client import DBClient
from ..dependencies import get_db

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()
SERVICE_REGISTRY_FILE = Path("/tmp/service_registry.json")

# --- V6.0 輔助函式：從註冊表獲取服務 URL ---
def get_service_url(service_name: str) -> str:
    """從服務註冊檔案中讀取微服務的 URL。"""
    if not SERVICE_REGISTRY_FILE.exists():
        raise RuntimeError("服務註冊檔案不存在，無法找到後端服務。")

    with open(SERVICE_REGISTRY_FILE, 'r') as f:
        registry = json.load(f)

    service_info = registry.get(service_name)
    if not service_info or service_info.get("status") != "running" or not service_info.get("port"):
        raise RuntimeError(f"服務 '{service_name}' 目前不可用或未註冊。")

    return f"http://127.0.0.1:{service_info['port']}"


# --- API 端點 (獲取列表) ---
@router.get("/pending_urls")
async def get_pending_urls(db: DBClient = Depends(get_db)):
    """獲取所有狀態為 'pending' 的網址列表。"""
    try:
        rows = db.get_urls_by_statuses(statuses=['pending'])
        return JSONResponse(content=[dict(row) for row in rows])
    except Exception as e:
        log.error(f"獲取待處理網址時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取待處理網址時發生伺服器內部錯誤。")

@router.get("/completed")
async def get_completed_downloads(db: DBClient = Depends(get_db)):
    """獲取所有狀態為 'completed' (已下載完成) 的檔案列表。"""
    try:
        rows = db.get_urls_by_statuses(statuses=['completed'])
        results = [{"id": r['id'], "url": r['url'], "filename": Path(r['local_path']).name, "completed_at": r['created_at']} for r in rows if r['local_path']]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"獲取已完成下載列表時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取已完成下載列表時發生伺服器內部錯誤。")


# --- Pydantic 模型 ---
class DownloadRequest(BaseModel):
    ids: List[int]

# --- 背景任務函式 (V6.0 重構為閘道模式) ---

def _call_downloader_service_blocking(url_id: int, db_client, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """
    執行單一檔案下載的同步阻塞部分。
    此版本將呼叫獨立的下載器微服務。
    """
    log.info(f"背景任務閘道：開始處理下載 URL ID: {url_id}")
    final_status = 'failed'
    status_message = ''

    try:
        # 步驟 1: 從主資料庫獲取下載所需的所有資訊
        url_record = db_client.get_url_by_id(url_id)
        if not url_record:
            raise ValueError(f"在資料庫中找不到 ID 為 {url_id} 的 URL。")

        # 步驟 2: 準備呼叫微服務的 payload
        payload = {
            "url": url_record['url'],
            "url_id": url_id,
            "author": url_record['author'],
            "message_date": url_record['message_date'],
            "message_time": url_record['message_time'],
        }
        log.info(f"背景任務閘道：準備呼叫下載器微服務，Payload: {payload}")

        # 步驟 3: 獲取微服務位址並發送請求
        downloader_url = get_service_url("downloader_service")
        response = requests.post(f"{downloader_url}/download", json=payload, timeout=600) # 10分鐘超時

        # 步驟 4: 處理微服務的回應
        if response.status_code == 200:
            result = response.json()
            downloaded_path = result.get("local_path")
            if result.get("status") == "success" and downloaded_path:
                final_status = 'completed'
                status_message = '下載成功'
                db_client.update_url(url_id, {"status": final_status, "local_path": downloaded_path, "status_message": status_message})
                log.info(f"背景任務閘道：微服務成功處理 URL ID {url_id}，路徑: {downloaded_path}")
            else:
                raise RuntimeError(f"下載器微服務回傳成功狀態碼，但缺少 'local_path'。回應: {result}")
        else:
            # 如果微服務回傳錯誤，將其記錄下來
            error_detail = response.text
            try:
                error_detail = response.json().get("detail", response.text)
            except json.JSONDecodeError:
                pass
            raise RuntimeError(f"下載器微服務回傳錯誤 {response.status_code}: {error_detail}")

    except Exception as e:
        log.error(f"背景任務閘道：處理 URL ID {url_id} 時發生嚴重錯誤: {e}", exc_info=True)
        final_status = 'failed'
        status_message = f"發生未預期錯誤: {e}"
        db_client.update_url(url_id, {"status": final_status, "status_message": status_message})
    finally:
        # 步驟 5: 無論成功或失敗，都將通知放入佇列
        final_record = db_client.get_url_by_id(url_id)
        notification_msg = {
            "type": "task_update", "task_type": "download", "task_id": str(url_id),
            "status": final_status, "result": final_record
        }
        asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)
        log.info(f"背景任務閘道：已為 URL ID {url_id} 發送完成通知至佇列。")


async def run_task_wrapper(task_id: int, semaphore: asyncio.Semaphore, blocking_func, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, **kwargs):
    """通用的非同步包裝函式，用於控制併發並執行阻塞的任務。"""
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
async def start_downloads(
    payload: DownloadRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: DBClient = Depends(get_db)
):
    """接收要下載的 URL ID 列表，並建立背景任務來呼叫下載器微服務。"""
    url_ids = payload.ids
    if not url_ids:
        raise HTTPException(status_code=400, detail="未提供要下載的 URL ID。")

    log.info(f"API 閘道：收到 {len(url_ids)} 個項目的下載請求。")

    semaphore = request.app.state.download_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()

    if not semaphore or not queue:
        raise HTTPException(status_code=500, detail="伺服器狀態未完全初始化（缺少佇列或信號量）。")

    try:
        for url_id in url_ids:
            db.update_url(url_id, {"status": "downloading", "status_message": "已加入下載佇列"})
        log.info(f"API 閘道：已將 {len(url_ids)} 個 URL 的狀態更新為 'downloading'。")

        for url_id in url_ids:
            background_tasks.add_task(
                run_task_wrapper,
                task_id=url_id,
                semaphore=semaphore,
                blocking_func=_call_downloader_service_blocking, # 使用新的閘道函式
                queue=queue,
                loop=loop,
                db_client=db
            )

        return JSONResponse(content={"message": f"已成功為 {len(url_ids)} 個項目建立背景下載任務。"})
    except Exception as e:
        log.error(f"API 閘道：啟動下載任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="啟動下載任務時發生伺服器內部錯誤。")
