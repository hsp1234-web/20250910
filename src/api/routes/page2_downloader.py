import logging
import sys
from pathlib import Path
import requests
import json

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from db.database import get_db_connection

# --- 常數與設定 ---
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()

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

# --- 背景任務函式 ---
def run_download_task(url_id: int, port: int):
    """
    這是在背景執行的單一檔案下載任務。
    它會處理下載、更新資料庫狀態，並在最後呼叫內部 API 以觸發 WebSocket 通知。
    """
    log.info(f"背景任務：開始處理下載 URL ID: {url_id}")
    conn = None
    final_status = 'failed' # 預設為失敗
    result_payload = {}

    try:
        # 步驟 1: 獲取所有命名所需的資訊
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT url, author, message_date, message_time FROM extracted_urls WHERE id = ?", (url_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"在資料庫中找不到 ID 為 {url_id} 的 URL。")

        url_to_download = row['url']
        author = row['author']
        message_date = row['message_date']
        message_time = row['message_time']
        log.info(f"背景任務：準備從 {url_to_download} 下載 (ID: {url_id})...")

        # 步驟 2: 執行智慧化下載
        from tools.drive_downloader import download_file
        download_dir = SRC_DIR.parent / "downloads"

        # 呼叫新的下載函式，傳入所有命名所需的資訊
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
            result_payload = {"local_path": downloaded_path}
            cursor.execute(
                "UPDATE extracted_urls SET status = ?, local_path = ?, status_message = '下載成功' WHERE id = ?",
                (final_status, downloaded_path, url_id)
            )
            log.info(f"背景任務：URL ID {url_id} 下載成功，路徑: {downloaded_path}")
        else:
            final_status = 'download_failed' # 使用更具體的狀態
            result_payload = {"error": "下載失敗，請檢查日誌"}
            cursor.execute(
                "UPDATE extracted_urls SET status = ?, status_message = '下載失敗，請檢查日誌' WHERE id = ?",
                (final_status, url_id)
            )
            log.error(f"背景任務：URL ID {url_id} 下載失敗。")

        conn.commit()

    except Exception as e:
        log.error(f"背景任務：處理 URL ID {url_id} 時發生嚴重錯誤: {e}", exc_info=True)
        final_status = 'failed'
        result_payload = {"error": str(e)}
        if conn and url_id:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE extracted_urls SET status = ?, status_message = ? WHERE id = ?",
                    (final_status, str(e), url_id)
                )
                conn.commit()
            except Exception as db_err:
                log.error(f"背景任務：在錯誤處理中更新資料庫狀態時再次失敗: {db_err}")
    finally:
        if conn:
            conn.close()

        # 步驟 4: 無論成功或失敗，都呼叫內部 API 來觸發 WebSocket 通知
        try:
            # 確保 task_id 在 payload 中是字串
            notification_payload = {
                "task_id": str(url_id),
                "status": final_status,
                "result": json.dumps(result_payload),
                "task_type": "download" # 新增類型，幫助後端區分
            }
            requests.post(
                f"http://127.0.0.1:{port}/api/internal/notify_task_update",
                json=notification_payload,
                timeout=5
            )
            log.info(f"背景任務：已為 URL ID {url_id} 發送完成通知。")
        except requests.exceptions.RequestException as e:
            log.error(f"背景任務：為 URL ID {url_id} 發送完成通知時失敗: {e}")


@router.post("/start_downloads")
async def start_downloads(payload: DownloadRequest, background_tasks: BackgroundTasks, request: Request):
    """
    接收要下載的 URL ID 列表，並為每一個 ID 建立一個背景下載任務。
    """
    url_ids = payload.ids
    if not url_ids:
        raise HTTPException(status_code=400, detail="未提供要下載的 URL ID。")

    log.info(f"API: 收到 {len(url_ids)} 個項目的下載請求。")

    # 從 app.state 獲取在應用程式啟動時捕獲的、可靠的伺服器埠號，
    # 而不是使用 request.url.port，因為後者在反向代理後可能不正確。
    port = request.app.state.server_port

    conn = None
    try:
        # 立即將所有請求的 URL 狀態更新為 'downloading'
        conn = get_db_connection()
        with conn:
            cursor = conn.cursor()
            # 使用 '?' 佔位符來安全地傳遞參數列表
            placeholders = ','.join('?' for _ in url_ids)
            sql = f"UPDATE extracted_urls SET status = 'downloading', status_message = '已加入下載佇列' WHERE id IN ({placeholders})"
            cursor.execute(sql, url_ids)
            log.info(f"API: 已將 {cursor.rowcount} 個 URL 的狀態更新為 'downloading'。")

        # 為每個 URL 新增一個背景任務
        for url_id in url_ids:
            background_tasks.add_task(run_download_task, url_id, port)

        return JSONResponse(
            content={"message": f"已成功為 {len(url_ids)} 個項目建立背景下載任務。"}
        )
    except Exception as e:
        log.error(f"API: 啟動下載任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="啟動下載任務時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()
