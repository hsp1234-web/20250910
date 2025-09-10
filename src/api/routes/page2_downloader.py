import logging
import sys
from pathlib import Path

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
    """
    log.info("API: 收到獲取待處理網址列表的請求。")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, url, created_at FROM extracted_urls WHERE status = 'pending' ORDER BY created_at DESC")
        rows = cursor.fetchall()
        results = [{"id": row[0], "url": row[1], "created_at": row[2]} for row in rows]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API: 獲取待處理網址時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取待處理網址時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()


# --- Pydantic 模型 ---
class DownloadRequest(BaseModel):
    ids: List[int]

# --- 背景任務函式 ---
def run_download_task(url_id: int):
    """
    這是在背景執行的單一檔案下載任務。
    它會處理下載、更新資料庫狀態等所有相關邏輯。
    """
    log.info(f"背景任務：開始處理下載 URL ID: {url_id}")
    conn = None
    url_to_download = None
    try:
        # 步驟 1: 獲取 URL 資訊
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM extracted_urls WHERE id = ?", (url_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"在資料庫中找不到 ID 為 {url_id} 的 URL。")

        url_to_download = row['url']
        log.info(f"背景任務：準備從 {url_to_download} 下載...")

        # 步驟 2: 執行下載
        from tools.drive_downloader import download_file
        # 將檔案下載到專案根目錄下的 'downloads' 資料夾
        download_dir = SRC_DIR.parent / "downloads"

        # 使用 url_id 作為檔名基礎，避免衝突
        # 注意：我們不知道副檔名，gdown 會自動處理
        file_name = f"download_{url_id}"

        downloaded_path = download_file(url_to_download, str(download_dir), file_name)

        # 步驟 3: 根據下載結果更新資料庫
        if downloaded_path:
            # 下載成功
            cursor.execute(
                "UPDATE extracted_urls SET status = 'completed', local_path = ?, status_message = '下載成功' WHERE id = ?",
                (downloaded_path, url_id)
            )
            log.info(f"背景任務：URL ID {url_id} 下載成功，路徑: {downloaded_path}")
        else:
            # 下載失敗
            cursor.execute(
                "UPDATE extracted_urls SET status = 'failed', status_message = '下載失敗，請檢查日誌' WHERE id = ?",
                (url_id,)
            )
            log.error(f"背景任務：URL ID {url_id} 下載失敗。")

        conn.commit()

    except Exception as e:
        log.error(f"背景任務：處理 URL ID {url_id} 時發生嚴重錯誤: {e}", exc_info=True)
        # 如果發生錯誤，也更新資料庫狀態
        if conn and url_id:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE extracted_urls SET status = 'failed', status_message = ? WHERE id = ?",
                    (str(e), url_id)
                )
                conn.commit()
            except Exception as db_err:
                log.error(f"背景任務：在錯誤處理中更新資料庫狀態時再次失敗: {db_err}")
    finally:
        if conn:
            conn.close()


@router.post("/start_downloads")
async def start_downloads(payload: DownloadRequest, background_tasks: BackgroundTasks):
    """
    接收要下載的 URL ID 列表，並為每一個 ID 建立一個背景下載任務。
    """
    url_ids = payload.ids
    if not url_ids:
        raise HTTPException(status_code=400, detail="未提供要下載的 URL ID。")

    log.info(f"API: 收到 {len(url_ids)} 個項目的下載請求。")

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
            background_tasks.add_task(run_download_task, url_id)

        return JSONResponse(
            content={"message": f"已成功為 {len(url_ids)} 個項目建立背景下載任務。"}
        )
    except Exception as e:
        log.error(f"API: 啟動下載任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="啟動下載任務時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()
