# src/api/routes/line_data_api.py
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, Request
from typing import List, Optional
import logging
import re

# --- 專案內部模組匯入 ---
from db.client import DBClient

# --- 日誌設定 ---
log = logging.getLogger('api_gateway')

# --- FastAPI 路由器 ---
router = APIRouter(
    prefix="/api/line_data",
    tags=["LINE Data Viewer"],
)

# --- 依賴注入 ---
def get_db_client():
    """提供一個 DBClient 的共享實例。"""
    return DBClient()

# --- 智慧排序輔助函式 ---
def natural_sort_key(s: str) -> list:
    """
    實現自然排序 (e.g., 'item2' comes before 'item10')。
    專為 '數字-名字' 的格式優化。
    """
    if s is None:
        return [float('inf'), '']
    # 嘗試用正則表達式匹配 '數字-名字' 的模式
    match = re.match(r'(\d+)-?(.*)', s)
    if match:
        # 如果匹配成功，回傳數字部分和文字部分
        return [int(match.group(1)), match.group(2).strip()]
    else:
        # 如果不匹配 (例如純文字)，將數字部分設為無窮大，使其排在後面
        return [float('inf'), s]

# --- API 端點 ---
@router.get("/items", summary="獲取所有 LINE 項目，並支援智慧排序")
async def get_all_line_items(
    sort_by: Optional[str] = Query('id', description="排序欄位"),
    sort_order: Optional[str] = Query('desc', description="排序順序 (asc/desc)"),
    db_client: DBClient = Depends(get_db_client)
):
    """
    從資料庫中獲取所有已匯入的 LINE 項目，並提供靈活的排序選項。
    """
    try:
        all_items = db_client.get_filtered_urls(source="line_importer") # 只獲取 LINE 匯入的項目
        if not all_items:
            return []

        # 執行排序
        reverse_order = sort_order.lower() == 'desc'

        if sort_by == 'author':
            # 如果是按作者排序，使用我們的智慧排序函式
            sorted_items = sorted(all_items, key=lambda item: natural_sort_key(item.get('author')), reverse=reverse_order)
        else:
            # 對於其他欄位，使用標準排序
            # 對於 None 值，我們將其視為最小值，以便在升序時排在最前面
            sorted_items = sorted(all_items, key=lambda item: (item.get(sort_by) is None, item.get(sort_by)), reverse=reverse_order)

        return sorted_items
    except Exception as e:
        log.error(f"從資料庫獲取 LINE 項目時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法從資料庫讀取項目清單。")

@router.get("/item/{item_id}", summary="獲取單一 LINE 項目的詳細資訊")
async def get_line_item_details(item_id: int, db_client: DBClient = Depends(get_db_client)):
    """
    根據 ID 獲取單個項目的所有詳細資料，用於編輯頁面。
    """
    try:
        item = db_client.get_url_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="找不到指定的項目。")
        return item
    except Exception as e:
        log.error(f"獲取項目 {item_id} 詳情時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="讀取項目詳情時發生錯誤。")

from pydantic import BaseModel

class ItemUpdate(BaseModel):
    extracted_text: Optional[str] = None
    ai_summary: Optional[str] = None

@router.put("/item/{item_id}", summary="更新單一 LINE 項目的詳細資訊")
async def update_line_item(
    item_id: int,
    update_data: ItemUpdate,
    db_client: DBClient = Depends(get_db_client)
):
    """
    更新指定項目的可編輯欄位，例如 extracted_text 和 ai_summary。
    """
    try:
        # Pydantic 的 model_dump(exclude_unset=True) 只會包含實際傳入的欄位
        updates = update_data.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail="請求中未包含任何要更新的資料。")

        success = db_client.update_url(item_id, updates)

        if not success:
            # 這可能是因為資料庫錯誤或找不到項目
            raise HTTPException(status_code=500, detail="更新資料庫時發生錯誤。")

        # 回傳更新後的完整項目
        updated_item = db_client.get_url_by_id(item_id)
        if not updated_item:
             raise HTTPException(status_code=404, detail="更新後找不到該項目。")

        return updated_item
    except HTTPException as e:
        raise e
    except Exception as e:
        log.error(f"更新項目 {item_id} 時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新項目時發生伺服器內部錯誤。")

@router.get("/pending_extraction", summary="獲取所有等待提取文字的 LINE 項目")
async def get_pending_extraction_items(db_client: DBClient = Depends(get_db_client)):
    """
    (Jules @ 2025-10-29)
    獲取所有來源為 'line_importer' 且提取狀態為 'pending' 的項目。
    這將用於新的手動處理介面，以處理舊資料。
    """
    try:
        # 1. 先獲取所有 line_importer 的項目
        all_line_items = db_client.get_filtered_urls(source="line_importer")
        if not all_line_items:
            return []

        # 2. 在應用程式層進行篩選
        pending_items = [
            item for item in all_line_items
            if item.get('status_extraction') == 'pending'
        ]

        return pending_items
    except Exception as e:
        log.error(f"獲取待提取項目時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法讀取待提取項目清單。")


# --- (Jules @ 2025-10-29) 背景處理邏輯 ---
# 為了建立手動處理舊 LINE 資料的功能，我們從 line_parser_service 中
# 借鏡並改寫了其核心處理工作流。

import asyncio
import functools
import time
from pathlib import Path
import json

from services.line_parser_service.universal_downloader import download_file
from services.line_parser_service.content_extractor import extract_content

def _run_line_extraction_blocking_task(url_id: int, db_client: DBClient):
    """
    這是在背景執行的、針對單一 LINE 項目的提取工作流。
    它只專注於「下載」和「提取」兩個步驟。
    """
    log.info(f"手動提取任務：開始處理項目 ID: {url_id}")
    time.sleep(1)

    try:
        url_record = db_client.get_url_by_id(url_id)
        if not url_record or not url_record.get('url'):
            raise ValueError(f"在資料庫中找不到 ID {url_id} 的有效 URL。")

        target_url = url_record['url']
        db_client.update_url(url_id, {"status_extraction": "processing", "status": "processing"})

        # --- 步驟 1: 下載 (如果需要) ---
        local_path = url_record.get('local_path')
        if not local_path or not Path(local_path).exists():
            log.info(f"手動提取任務 [ID: {url_id}]: 找不到本地檔案，開始下載: {target_url}")
            download_dir = Path("downloads") / "line_manual_downloads"
            download_dir.mkdir(parents=True, exist_ok=True)

            # (Jules @ 2025-10-29) 修正: 呼叫正確的函式並處理其回傳值 (tuple)
            success, result_path, result_type = download_file(target_url, str(download_dir))

            if not success:
                error_msg = result_path # 失敗時，result_path 包含錯誤訊息
                raise RuntimeError(f"下載失敗: {error_msg}")

            # 確保我們只處理檔案，而非目錄
            if result_type == 'directory':
                 raise RuntimeError(f"下載成功，但目標是一個目錄，無法進行提取: {result_path}")

            local_path = result_path
            db_client.update_url(url_id, {"local_path": local_path, "status_download": "success"})
        else:
            log.info(f"手動提取任務 [ID: {url_id}]: 已找到本地快取檔案: {local_path}")


        # --- 步驟 2: 提取 ---
        log.info(f"手動提取任務 [ID: {url_id}]: 開始從 {local_path} 提取內容。")
        file_path = Path(local_path)
        image_output_dir = file_path.parent / f"extracted_images_{url_id}"

        content_data = extract_content(str(file_path), str(image_output_dir))
        text_content = content_data.get("text", "")

        update_payload = {
            "status_extraction": "success",
            "extracted_text": text_content,
            "status": "processed" if text_content else "processed_unsupported",
            "last_error_details": None
        }
        db_client.update_url(url_id, update_payload)
        log.info(f"✅ 手動提取任務 [ID: {url_id}]: 處理成功。")

    except Exception as e:
        error_message = f"處理項目 ID {url_id} 時發生錯誤: {e}"
        log.error(error_message, exc_info=True)
        db_client.update_url(url_id, {
            "status_extraction": "failed",
            "status": "processing_failed",
            "last_error_details": error_message
        })

async def run_task_wrapper(task_id: int, semaphore: asyncio.Semaphore, blocking_func, db_client: DBClient):
    """非同步包裝函式，用於控制併發執行阻塞任務。"""
    async with semaphore:
        loop = asyncio.get_running_loop()
        try:
            partial_func = functools.partial(blocking_func, url_id=task_id, db_client=db_client)
            await loop.run_in_executor(None, partial_func)
        except Exception as e:
            log.error(f"任務包裝函式捕獲到未預期錯誤 (任務 {task_id}): {e}", exc_info=True)

class ExtractionRequest(BaseModel):
    ids: List[int]

@router.post("/start_extraction", summary="啟動手動提取任務")
async def start_extraction(
    payload: ExtractionRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db_client: DBClient = Depends(get_db_client)
):
    """
    (Jules @ 2025-10-29)
    接收要手動處理的 LINE 項目 ID 列表，並為其建立背景提取任務。
    """
    url_ids = payload.ids
    if not url_ids:
        raise HTTPException(status_code=400, detail="未提供要處理的項目 ID。")

    log.info(f"API: 收到 {len(url_ids)} 個 LINE 項目的手動提取請求。")

    semaphore = getattr(request.app.state, "processing_semaphore", None)
    if not semaphore:
        log.warning("在 app.state 中找不到 processing_semaphore，將建立一個預設信號量。")
        semaphore = asyncio.Semaphore(5)

    try:
        for url_id in url_ids:
            db_client.update_url(url_id, {"status_extraction": "processing", "status": "processing"})

        for url_id in url_ids:
            background_tasks.add_task(
                run_task_wrapper,
                task_id=url_id,
                semaphore=semaphore,
                blocking_func=_run_line_extraction_blocking_task,
                db_client=db_client
            )

        return {"message": f"已成功為 {len(url_ids)} 個項目啟動背景提取任務。"}

    except Exception as e:
        log.error(f"啟動提取任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="啟動提取任務時發生伺服器內部錯誤。")