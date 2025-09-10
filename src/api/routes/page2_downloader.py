import logging
import sys
import os
import asyncio
from pathlib import Path
from typing import List, Coroutine

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from db.database import get_db_connection
# 從共享模組匯入 WebSocket 管理器，避免循環依賴
from api.connection_manager import manager as ws_manager
# 匯入我們重構後的下載工具
from tools.drive_downloader import download_file

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()
DOWNLOAD_DIR = SRC_DIR.parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True) # 確保下載目錄存在

# --- 輔助函式 ---
def is_image_file(filename: str) -> bool:
    """根據副檔名判斷檔案是否為圖片。"""
    if not filename:
        return False
    return filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg'))

def broadcast_message(loop: asyncio.AbstractEventLoop, message: dict):
    """安全地從背景執行緒廣播 WebSocket 訊息。"""
    if loop and loop.is_running():
        # 使用 run_coroutine_threadsafe 在事件迴圈中執行非同步的廣播函式
        asyncio.run_coroutine_threadsafe(ws_manager.broadcast_json(message), loop)
    else:
        log.warning("事件迴圈未執行，無法廣播 WebSocket 訊息。")

# --- API 端點 ---
@router.get("/pending_urls")
async def get_pending_urls():
    """獲取所有狀態為 'pending' 的網址列表。"""
    log.info("API: 收到獲取待處理網址列表的請求。")
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, url, created_at FROM extracted_urls WHERE status = 'pending' ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [{"id": row[0], "url": row[1], "created_at": row[2]} for row in rows]
    except Exception as e:
        log.error(f"API: 獲取待處理網址時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取待處理網址時發生伺服器內部錯誤。")

# --- Pydantic 模型 ---
class DownloadRequest(BaseModel):
    ids: List[int]

# --- 背景任務函式 ---
def run_download_task(url_id: int, loop: asyncio.AbstractEventLoop):
    """
    這是在背景執行的單一檔案下載任務。
    它會處理下載、透過 WebSocket 發送即時進度，並在最後更新資料庫。
    """
    log.info(f"背景任務：開始處理下載 URL ID: {url_id}")
    url_to_download = None
    task_final_status = 'failed'
    final_message = f"下載 URL ID {url_id} 時發生未知錯誤。"
    downloaded_file_path = None

    try:
        # 步驟 1: 獲取 URL 資訊
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM extracted_urls WHERE id = ?", (url_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"在資料庫中找不到 ID 為 {url_id} 的 URL。")
            url_to_download = row['url']

        log.info(f"背景任務：準備從 {url_to_download} 下載...")

        # 使用 url_id 作為檔名基礎，避免衝突
        file_name_base = f"download_{url_id}"

        # 步驟 2: 疊代處理下載生成器
        for update in download_file(url_to_download, str(DOWNLOAD_DIR), file_name_base):
            if update['type'] == 'progress':
                # 廣播進度更新
                progress_payload = {"task_id": url_id, "progress": update['value']}
                broadcast_message(loop, {"type": "DOWNLOAD_PROGRESS", "payload": progress_payload})

            elif update['type'] == 'completed':
                # 下載成功
                downloaded_file_path = update['path']
                final_filename = os.path.basename(downloaded_file_path)
                task_final_status = 'completed'
                final_message = '下載成功'
                log.info(f"背景任務：URL ID {url_id} 下載成功，路徑: {downloaded_file_path}")

                # 廣播完成訊息
                complete_payload = {
                    "task_id": url_id,
                    "file_path": f"/downloads/{final_filename}", # 提供給前端的相對路徑
                    "file_name": final_filename,
                    "is_image": is_image_file(final_filename)
                }
                broadcast_message(loop, {"type": "DOWNLOAD_COMPLETE", "payload": complete_payload})
                break # 完成後退出迴圈

            elif update['type'] == 'error':
                # 下載過程中發生錯誤
                final_message = update['message']
                log.error(f"背景任務：URL ID {url_id} 下載失敗: {final_message}")
                # 廣播錯誤訊息
                error_payload = {"task_id": url_id, "error": final_message}
                broadcast_message(loop, {"type": "DOWNLOAD_ERROR", "payload": error_payload})
                break # 發生錯誤後退出迴圈

    except Exception as e:
        final_message = f"處理 URL ID {url_id} 時發生嚴重錯誤: {e}"
        log.error(f"背景任務：{final_message}", exc_info=True)
        # 廣播錯誤訊息
        error_payload = {"task_id": url_id, "error": str(e)}
        broadcast_message(loop, {"type": "DOWNLOAD_ERROR", "payload": error_payload})

    finally:
        # 步驟 3: 無論成功或失敗，最後都在資料庫中更新最終狀態
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE extracted_urls SET status = ?, local_path = ?, status_message = ? WHERE id = ?",
                    (task_final_status, downloaded_file_path, final_message, url_id)
                )
            log.info(f"背景任務：已將 URL ID {url_id} 的最終狀態更新為 '{task_final_status}'。")
        except Exception as db_err:
            log.error(f"背景任務：在更新 URL ID {url_id} 的最終狀態時發生資料庫錯誤: {db_err}")


@router.post("/start_downloads")
async def start_downloads(request: Request, payload: DownloadRequest, background_tasks: BackgroundTasks):
    """
    接收要下載的 URL ID 列表，並為每一個 ID 建立一個背景下載任務。
    """
    url_ids = payload.ids
    if not url_ids:
        raise HTTPException(status_code=400, detail="未提供要下載的 URL ID。")

    log.info(f"API: 收到 {len(url_ids)} 個項目的下載請求。")

    try:
        # 立即將所有請求的 URL 狀態更新為 'downloading'
        with get_db_connection() as conn:
            placeholders = ','.join('?' for _ in url_ids)
            sql = f"UPDATE extracted_urls SET status = 'downloading', status_message = '已加入下載佇列' WHERE id IN ({placeholders})"
            cursor = conn.cursor()
            cursor.execute(sql, url_ids)
            log.info(f"API: 已將 {cursor.rowcount} 個 URL 的狀態更新為 'downloading'。")

        # 獲取當前的事件迴圈，以便傳遞給背景任務來發送 WebSocket 訊息
        loop = asyncio.get_running_loop()

        # 為每個 URL 新增一個背景任務，並傳入事件迴圈
        for url_id in url_ids:
            background_tasks.add_task(run_download_task, url_id, loop)
            # 初始廣播，讓前端可以立刻建立進度條
            initial_payload = {"task_id": url_id}
            # FastAPI 的 request 物件包含 app 實例，但直接使用 ws_manager 更簡單
            await ws_manager.broadcast_json({"type": "DOWNLOAD_STARTED", "payload": initial_payload})


        return JSONResponse(
            content={"message": f"已成功為 {len(url_ids)} 個項目建立背景下載任務。"}
        )
    except Exception as e:
        log.error(f"API: 啟動下載任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="啟動下載任務時發生伺服器內部錯誤。")
