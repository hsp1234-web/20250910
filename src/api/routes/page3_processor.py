import logging
import sys
from pathlib import Path
import json
import asyncio
import functools
import time

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from db.database import get_db_connection
# V4 優化：移除 get_client，改為依賴注入
# from db.client import get_client
from db.client import DBClient
from ..dependencies import get_db
from tools.file_hasher import calculate_sha256
from tools.image_compressor import compress_image
from fastapi import Depends

# --- 常數與設定 ---
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()
# V4 優化：移除在模組加載時建立的客戶端實例。
# DB_CLIENT = get_client()

# --- Pydantic 模型 ---
class ProcessRequest(BaseModel):
    ids: List[int]

class ResetRequest(BaseModel):
    ids: List[int]

# --- API 端點 ---
@router.get("/terminal_files")
async def get_terminal_files():
    """獲取所有已進入終端狀態 (processed, processed_unsupported, processing_failed) 的檔案列表。"""
    log.info("API: 收到獲取所有終端狀態檔案列表的請求。")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # 查詢所有已結束處理的狀態
        cursor.execute("""
            SELECT id, url, local_path, status, status_message
            FROM extracted_urls
            WHERE status IN ('processed', 'processed_unsupported', 'processing_failed')
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        results = [
            {
                "id": row['id'],
                "url": row['url'],
                "filename": Path(row['local_path']).name if row['local_path'] else 'N/A',
                "status": row['status'],
                "status_message": row['status_message']
            }
            for row in rows
        ]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API: 獲取終端狀態檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取終端狀態檔案時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()


@router.post("/reset_files")
async def reset_files(payload: ResetRequest, db: DBClient = Depends(get_db)):
    """(V4 優化後) 將指定 ID 的檔案狀態重設回 'completed'，以便重新處理。"""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="未提供要重設的檔案 ID。")

    log.info(f"API: 收到將 {len(payload.ids)} 個檔案狀態重設為 'completed' 的請求。")
    try:
        # V4 優化：使用透過 Depends 注入的共享 db 實例
        updated_count = 0
        for url_id in payload.ids:
            success = db.update_url(url_id, {"status": "completed", "status_message": "等待重新處理"})
            if success:
                updated_count += 1

        if updated_count == 0:
            log.warning(f"API: 重設檔案狀態時，沒有任何 ID ({payload.ids}) 被更新。")
            raise HTTPException(status_code=404, detail="提供的 ID 在資料庫中不存在或無法被重設。")

        log.info(f"API: 已成功將 {updated_count} 個檔案的狀態更新為 'completed'。")
        return JSONResponse(content={"message": f"成功重設 {updated_count} 個檔案。", "reset_ids": payload.ids})
    except Exception as e:
        log.error(f"API: 重設檔案狀態時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="重設檔案狀態時發生伺服器內部錯誤。")


@router.get("/completed_files")
async def get_completed_files():
    """獲取所有狀態為 'completed' (已下載完成) 的檔案列表。"""
    log.info("API: 收到獲取已下載檔案列表的請求。")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, url, local_path FROM extracted_urls WHERE status = 'completed' ORDER BY created_at DESC")
        rows = cursor.fetchall()
        results = [{"id": row['id'], "url": row['url'], "filename": Path(row['local_path']).name} for row in rows if row['local_path']]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API: 獲取已下載檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取已下載檔案時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()


@router.get("/processed")
async def get_processed_files():
    """
    獲取所有狀態為 'processed' (已處理完成) 的檔案列表。
    這是為了在頁面三顯示已處理的報告。
    """
    log.info("API: 收到獲取已處理報告列表的請求。")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # 選擇 file_hash 也是為了將來可能的用途
        cursor.execute("SELECT id, local_path FROM extracted_urls WHERE status = 'processed' ORDER BY created_at DESC")
        rows = cursor.fetchall()
        results = [
            {
                "id": row['id'],
                "filename": Path(row['local_path']).name
            }
            for row in rows if row['local_path']
        ]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API: 獲取已處理報告列表時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取已處理報告列表時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()


@router.get("/report/{file_id}")
async def get_report_content(file_id: int):
    """
    獲取單一已處理報告的詳細內容，包括文字和壓縮後的圖片路徑。
    """
    log.info(f"API: 收到對檔案 ID {file_id} 的報告內容請求。")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT extracted_text, extracted_image_paths FROM extracted_urls WHERE id = ? AND status = 'processed'",
            (file_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="找不到指定 ID 的已處理報告。")

        # 從資料庫獲取真實的文字內容
        text_content = row['extracted_text'] or "沒有可用的文字內容。"

        # 處理圖片
        compressed_image_paths = []
        original_image_paths_json = row['extracted_image_paths']
        if original_image_paths_json:
            original_image_paths = json.loads(original_image_paths_json)

            # 定義壓縮圖片的儲存目錄
            compressed_output_dir = SRC_DIR.parent / "downloads" / "compressed_images"

            for img_path in original_image_paths:
                compressed_path = compress_image(img_path, str(compressed_output_dir))
                if compressed_path:
                    # 我們需要回傳一個可從前端訪問的相對 URL 路徑
                    web_path = Path(compressed_path).relative_to(SRC_DIR.parent).as_posix()
                    compressed_image_paths.append(web_path)

        return JSONResponse(content={
            "text_content": text_content,
            "image_paths": compressed_image_paths
        })

    except Exception as e:
        log.error(f"API: 獲取報告 ID {file_id} 的內容時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取報告內容時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()


# --- 背景任務函式 (重構後) ---

def _run_processing_blocking_task(url_id: int, db_client, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """這是在背景執行的單一檔案處理的同步阻塞部分。"""
    # --- 延遲導入 (Lazy Import) ---
    from tools.content_extractor import extract_content

    time.sleep(1) # 為解決檔案系統競爭條件，在開始時增加一個短暫的延遲

    log.info(f"背景任務：開始處理檔案 URL ID: {url_id}")
    final_status = 'processing_failed' # 預設為失敗
    file_path = None  # 初始化 file_path 以確保在 finally 區塊中可用

    try:
        url_record = db_client.get_url_by_id(url_id)
        if not url_record or not url_record['local_path']:
             raise ValueError(f"在資料庫中找不到 ID {url_id} 的有效本地檔案路徑。")

        file_path = Path(url_record['local_path'])
        if not file_path.is_file():
            raise FileNotFoundError(f"檔案系統中找不到檔案: {file_path}")

        log.info(f"背景任務：準備處理檔案: {file_path}")

        file_hash = calculate_sha256(file_path)
        image_output_dir = file_path.parent / "extracted_images"
        content_data = extract_content(str(file_path), str(image_output_dir))

        text_content = content_data.get("text", "") if content_data else ""
        image_paths_json = json.dumps(content_data.get("image_paths", [])) if content_data else "[]"

        if not text_content and not json.loads(image_paths_json):
            status = 'processed_unsupported'
            status_message = '不支援的檔案類型或檔案為空，無法提取任何內容。'
        else:
            status = 'processed'
            status_message = '處理成功'

        update_payload = {
            "status": status,
            "status_message": status_message,
            "file_hash": file_hash,
            "extracted_image_paths": image_paths_json,
            "extracted_text": text_content
        }
        db_client.update_url(url_id, update_payload)

        analysis_task = db_client.create_or_get_analysis_task(file_id=url_id, filename=file_path.name)
        if analysis_task:
            analysis_task_id = analysis_task['id']
            db_client.update_analysis_task(analysis_task_id, {'file_content_for_analysis': text_content})
            log.info(f"成功將提取的文字內容儲存至分析任務 ID: {analysis_task_id}")
        else:
            log.error(f"無法為 file_id {url_id} 建立或取得分析任務，無法儲存提取文字。")

        final_status = status
        log.info(f"背景任務：URL ID {url_id} 處理成功。")

    except Exception as e:
        log.error(f"背景任務：處理 URL ID {url_id} 時發生嚴重錯誤: {e}", exc_info=True)
        final_status = 'processing_failed'
        db_client.update_url(url_id, {"status": final_status, "status_message": str(e)})
    finally:
        final_record = db_client.get_url_by_id(url_id)
        notification_msg = {
            "type": "task_update",
            "task_type": "processing",
            "task_id": str(url_id),
            "status": final_status,
            "result": final_record
        }
        asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)
        log.info(f"背景任務：已為 URL ID {url_id} 發送處理完成通知至佇列。")


async def run_task_wrapper(task_id: int, semaphore: asyncio.Semaphore, blocking_func, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, **kwargs):
    """一個通用的非同步包裝函式，用於控制併發並執行阻塞的任務。"""
    async with semaphore:
        log.info(f"任務 {task_id} 已取得信號量，準備執行...")
        try:
            partial_func = functools.partial(blocking_func, url_id=task_id, queue=queue, loop=loop, **kwargs)
            await loop.run_in_executor(None, partial_func)
        except Exception as e:
            log.error(f"包裝函式捕獲到未預期的錯誤 (任務 {task_id}): {e}", exc_info=True)
        finally:
            log.info(f"任務 {task_id} 執行完畢，釋放信號量。")


@router.post("/start_processing")
async def start_processing(
    payload: ProcessRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: DBClient = Depends(get_db)
):
    """(V4 優化後) 接收要處理的檔案 ID 列表，並使用共享的 DBClient 實例來建立背景任務。"""
    url_ids = payload.ids
    if not url_ids:
        raise HTTPException(status_code=400, detail="未提供要處理的檔案 ID。")

    log.info(f"API: 收到 {len(url_ids)} 個項目的處理請求。")

    semaphore = request.app.state.processing_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()

    if not semaphore or not queue:
        raise HTTPException(status_code=500, detail="伺服器狀態未完全初始化（缺少佇列或信號量）。")

    try:
        # V4 優化：使用透過 Depends 注入的共享 db 實例
        for url_id in url_ids:
            db.update_url(url_id, {"status": "processing", "status_message": "已加入處理佇列"})
        log.info(f"API: 已將 {len(url_ids)} 個檔案的狀態更新為 'processing'。")

        for url_id in url_ids:
            background_tasks.add_task(
                run_task_wrapper,
                task_id=url_id,
                semaphore=semaphore,
                blocking_func=_run_processing_blocking_task,
                queue=queue,
                loop=loop,
                db_client=db  # V4 優化：將共享的 db 實例傳遞到背景任務中
            )

        return JSONResponse(
            content={"message": f"已成功為 {len(url_ids)} 個項目建立背景處理任務。"}
        )
    except Exception as e:
        log.error(f"API: 啟動處理任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="啟動處理任務時發生伺服器內部錯誤。")
