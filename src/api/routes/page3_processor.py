import logging
import sys
from pathlib import Path
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
from tools.file_hasher import calculate_sha256
from tools.content_extractor import extract_content

# --- 常數與設定 ---
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()

# --- Pydantic 模型 ---
class ProcessRequest(BaseModel):
    ids: List[int]

# --- API 端點 ---
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

# --- 背景任務函式 ---
def run_processing_task(url_id: int):
    """這是在背景執行的單一檔案處理任務。"""
    log.info(f"背景任務：開始處理檔案 URL ID: {url_id}")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT local_path FROM extracted_urls WHERE id = ?", (url_id,))
        row = cursor.fetchone()
        if not row or not row['local_path']:
            raise ValueError(f"在資料庫中找不到 ID {url_id} 的有效本地檔案路徑。")

        file_path = Path(row['local_path'])
        if not file_path.is_file():
            raise FileNotFoundError(f"檔案系統中找不到檔案: {file_path}")

        log.info(f"背景任務：準備處理檔案: {file_path}")

        file_hash = calculate_sha256(file_path)

        image_output_dir = file_path.parent / "extracted_images"
        content_data = extract_content(str(file_path), str(image_output_dir))
        image_paths_json = json.dumps(content_data.get("image_paths", [])) if content_data else "[]"

        cursor.execute(
            """
            UPDATE extracted_urls
            SET status = 'processed', status_message = '處理成功', file_hash = ?, extracted_image_paths = ?
            WHERE id = ?
            """,
            (file_hash, image_paths_json, url_id)
        )
        conn.commit()
        log.info(f"背景任務：URL ID {url_id} 處理成功。")

    except Exception as e:
        log.error(f"背景任務：處理 URL ID {url_id} 時發生嚴重錯誤: {e}", exc_info=True)
        if conn and url_id:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE extracted_urls SET status = 'processing_failed', status_message = ? WHERE id = ?",
                    (str(e), url_id)
                )
                conn.commit()
            except Exception as db_err:
                log.error(f"背景任務：在錯誤處理中更新資料庫狀態時再次失敗: {db_err}")
    finally:
        if conn:
            conn.close()

@router.post("/api/start_processing")
async def start_processing(payload: ProcessRequest, background_tasks: BackgroundTasks):
    """接收要處理的檔案 ID 列表，並為每一個 ID 建立一個背景處理任務。"""
    url_ids = payload.ids
    if not url_ids:
        raise HTTPException(status_code=400, detail="未提供要處理的檔案 ID。")

    log.info(f"API: 收到 {len(url_ids)} 個項目的處理請求。")

    conn = None
    try:
        conn = get_db_connection()
        with conn:
            placeholders = ','.join('?' for _ in url_ids)
            sql = f"UPDATE extracted_urls SET status = 'processing', status_message = '已加入處理佇列' WHERE id IN ({placeholders})"
            cursor = conn.cursor()
            cursor.execute(sql, url_ids)
            log.info(f"API: 已將 {cursor.rowcount} 個檔案的狀態更新為 'processing'。")

        for url_id in url_ids:
            background_tasks.add_task(run_processing_task, url_id)

        return JSONResponse(
            content={"message": f"已成功為 {len(url_ids)} 個項目建立背景處理任務。"}
        )
    except Exception as e:
        log.error(f"API: 啟動處理任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="啟動處理任務時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()
