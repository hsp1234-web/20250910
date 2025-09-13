import logging
import sys
from pathlib import Path
import json
import requests

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
from tools.image_compressor import compress_image

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


# --- 背景任務函式 ---
import time

def run_processing_task(url_id: int, port: int):
    """這是在背景執行的單一檔案處理任務。"""
    # --- 延遲導入 (Lazy Import) ---
    from tools.content_extractor import extract_content
    from db.client import get_client

    # 為解決檔案系統競爭條件，在開始時增加一個短暫的延遲
    time.sleep(1)

    log.info(f"背景任務：開始處理檔案 URL ID: {url_id}")
    db_client = get_client()
    final_status = 'processing_failed' # 預設為失敗
    result_payload = {}
    file_path = None  # 初始化 file_path 以確保在 finally 區塊中可用

    try:
        # 使用 DBClient 而非直接的 conn
        url_record = db_client.get_url_by_id(url_id)
        if not url_record or not url_record.get('local_path'):
             raise ValueError(f"在資料庫中找不到 ID {url_id} 的有效本地檔案路徑。")

        file_path = Path(url_record['local_path'])
        if not file_path.is_file():
            raise FileNotFoundError(f"檔案系統中找不到檔案: {file_path}")

        log.info(f"背景任務：準備處理檔案: {file_path}")

        file_hash = calculate_sha256(file_path)

        image_output_dir = file_path.parent / "extracted_images"
        content_data = extract_content(str(file_path), str(image_output_dir))

        # 從提取結果中獲取文字和圖片路徑
        text_content = content_data.get("text", "") if content_data else ""
        image_paths_json = json.dumps(content_data.get("image_paths", [])) if content_data else "[]"

        # 檢查內容提取是否成功，並設定對應的狀態
        if not text_content and not json.loads(image_paths_json):
            # 如果文字和圖片都為空，標記為不支援或空檔案
            status = 'processed_unsupported'
            status_message = '不支援的檔案類型或檔案為空，無法提取任何內容。'
        else:
            status = 'processed'
            status_message = '處理成功'

        # 更新 extracted_urls 表
        update_payload = {
            "status": status,
            "status_message": status_message,
            "file_hash": file_hash,
            "extracted_image_paths": image_paths_json,
            "extracted_text": text_content
        }
        db_client.update_url(url_id, update_payload)

        # *** 核心邏輯修改：將提取的文字儲存到 analysis_tasks 表 ***
        analysis_task = db_client.create_or_get_analysis_task(file_id=url_id, filename=file_path.name)
        if analysis_task:
            analysis_task_id = analysis_task['id']
            update_result = db_client.update_analysis_task(
                analysis_task_id,
                {'file_content_for_analysis': text_content}
            )
            if update_result:
                log.info(f"成功將提取的文字內容儲存至分析任務 ID: {analysis_task_id}")
            else:
                log.error(f"無法將提取的文字內容儲存至分析任務 ID: {analysis_task_id}")
        else:
            log.error(f"無法為 file_id {url_id} 建立或取得分析任務，無法儲存提取文字。")
        # *** 結束核心修改 ***

        final_status = 'processed'
        result_payload = {"file_hash": file_hash, "image_paths": image_paths_json, "text_length": len(text_content)}
        log.info(f"背景任務：URL ID {url_id} 處理成功。")

    except Exception as e:
        log.error(f"背景任務：處理 URL ID {url_id} 時發生嚴重錯誤: {e}", exc_info=True)
        final_status = 'processing_failed'
        result_payload = {"error": str(e)}
        # 使用 DBClient 更新錯誤狀態
        db_client.update_url(url_id, {"status": final_status, "status_message": str(e)})
    finally:
        # 步驟 4: 無論成功或失敗，都呼叫內部 API 來觸發 WebSocket 通知
        try:
            notification_payload = {
                "task_id": str(url_id),
                "status": final_status,
                "result": json.dumps(result_payload),
                "task_type": "processing"
            }
            # 將檔名加入 payload，以便前端顯示更清晰的日誌
            if file_path:
                notification_payload["filename"] = file_path.name

            requests.post(
                f"http://127.0.0.1:{port}/api/internal/notify_task_update",
                json=notification_payload,
                timeout=5
            )
            log.info(f"背景任務：已為 URL ID {url_id} 發送處理完成通知。")
        except requests.exceptions.RequestException as e:
            log.error(f"背景任務：為 URL ID {url_id} 發送處理完成通知時失敗: {e}")

@router.post("/start_processing")
async def start_processing(payload: ProcessRequest, background_tasks: BackgroundTasks, request: Request):
    """接收要處理的檔案 ID 列表，並為每一個 ID 建立一個背景處理任務。"""
    url_ids = payload.ids
    if not url_ids:
        raise HTTPException(status_code=400, detail="未提供要處理的檔案 ID。")

    log.info(f"API: 收到 {len(url_ids)} 個項目的處理請求。")

    # 從 app.state 獲取在應用程式啟動時捕獲的、可靠的伺服器埠號，
    # 而不是使用 request.url.port，因為後者在反向代理後可能不正確。
    port = request.app.state.server_port

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
            background_tasks.add_task(run_processing_task, url_id, port)

        return JSONResponse(
            content={"message": f"已成功為 {len(url_ids)} 個項目建立背景處理任務。"}
        )
    except Exception as e:
        log.error(f"API: 啟動處理任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="啟動處理任務時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()
