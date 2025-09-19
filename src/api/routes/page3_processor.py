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

# V4 優化：移除 get_db_connection，全面改用依賴注入
# from db.database import get_db_connection
from db.client import DBClient
from ..dependencies import get_db
# JULES V6 啟動優化：延遲載入
# from tools.file_hasher import calculate_sha256
# from tools.image_compressor import compress_image
from fastapi import Depends

# --- 常數與設定 ---
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()

# JULES (2025-09-17): 暫時加回 DB_CLIENT 全域變數，以相容舊的整合測試。
# 這些測試使用 monkeypatch 來修補這個變數，但在 V4 重構後它已被移除。
# 長期解決方案是重寫測試以使用 FastAPI 的依賴注入覆蓋機制。
DB_CLIENT = DBClient()


# --- Pydantic 模型 ---
class ProcessRequest(BaseModel):
    ids: List[int]

class ResetRequest(BaseModel):
    ids: List[int]

# --- API 端點 ---
@router.get("/terminal_files")
async def get_terminal_files(db: DBClient = Depends(get_db)):
    """(V4 優化後) 獲取所有已進入終端狀態的檔案列表。"""
    log.info("API: 收到獲取所有終端狀態檔案列表的請求。")
    try:
        statuses = ['processed', 'processed_unsupported', 'processing_failed']
        rows = db.get_urls_by_statuses(statuses=statuses)
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
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail="獲取終端狀態檔案時發生伺服器內部錯誤。")


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
async def get_completed_files(db: DBClient = Depends(get_db)):
    """(V4 優化後) 獲取所有狀態為 'completed' (已下載完成) 的檔案列表。"""
    log.info("API: 收到獲取已下載檔案列表的請求。")
    try:
        rows = db.get_urls_by_statuses(statuses=['completed'])
        results = [{"id": row['id'], "url": row['url'], "filename": Path(row['local_path']).name} for row in rows if row['local_path']]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API: 獲取已下載檔案時發生錯誤: {e}", exc_info=True)
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail="獲取已下載檔案時發生伺服器內部錯誤。")


@router.get("/processed")
async def get_processed_files(db: DBClient = Depends(get_db)):
    """(V4 優化後) 獲取所有狀態為 'processed' (已處理完成) 的檔案列表。"""
    log.info("API: 收到獲取已處理報告列表的請求。")
    try:
        rows = db.get_urls_by_statuses(statuses=['processed'])
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
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail="獲取已處理報告列表時發生伺服器內部錯誤。")


@router.get("/report/{file_id}")
async def get_report_content(file_id: int, db: DBClient = Depends(get_db)):
    """(V4 優化後) 獲取單一已處理報告的詳細內容。"""
    log.info(f"API: 收到對檔案 ID {file_id} 的報告內容請求。")
    try:
        # JULES V6 啟動優化：延遲載入
        from tools.image_compressor import compress_image

        row = db.get_url_by_id(url_id=file_id)
        if not row or row['status'] != 'processed':
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
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail="獲取報告內容時發生伺服器內部錯誤。")


# JULES (V7 微服務重構):
# 移除了 _run_processing_blocking_task, run_task_wrapper, 和 /start_processing 端點。
# 檔案處理的觸發機制已完全轉移到由 Redis 訊息驅動的 `processor_service`。
# 這個 API 檔案現在只負責提供查詢處理狀態和結果的介面。
