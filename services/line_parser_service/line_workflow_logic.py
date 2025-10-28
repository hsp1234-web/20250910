# services/line_parser_service/line_workflow_logic.py

import logging
import sys
from pathlib import Path
import json
import asyncio
import time
import functools

# --- 路徑修正與模組匯入 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 這裡的 db_client 會在被呼叫時傳入
# from src.db.client import DBClient
from src.db.database import get_db_connection

log = logging.getLogger(__name__)


def _run_line_item_processing_task(url_id: int, db_client, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """
    [V2 - 全新改造]
    這是在背景執行的、針對單一 LINE 項目的完整處理工作流。
    它負責從一個 URL 開始，完成「下載」 -> 「提取」 -> 「更新資料庫」的完整流程。
    """
    # --- 核心工具延遲導入 (Lazy Import) ---
    from .universal_downloader import download
    from .content_extractor import extract_content

    log.info(f"LINE 工作流：開始處理項目 ID: {url_id}")
    time.sleep(1) # 短暫延遲以避免檔案系統競爭條件

    try:
        # --- 步驟 0: 獲取初始資料 ---
        url_record = db_client.get_url_by_id(url_id)
        if not url_record or not url_record.get('url'):
            raise ValueError(f"在資料庫中找不到 ID {url_id} 的有效 URL 紀錄。")

        target_url = url_record['url']
        log.info(f"LINE 工作流 [ID: {url_id}]: 準備下載 URL: {target_url}")

        # --- 步驟 1: 下載 ---
        # 更新狀態為下載中
        db_client.update_url(url_id, {"status_download": "processing", "status": "processing"})

        # 定義下載目錄
        download_dir = Path(__file__).resolve().parent / "downloads"
        download_dir.mkdir(exist_ok=True)

        download_result = download(target_url, str(download_dir))

        local_path = download_result.get("local_path")
        if not local_path or download_result.get("error"):
            error_message = download_result.get("error", "未知的下載錯誤")
            log.error(f"LINE 工作流 [ID: {url_id}]: 下載失敗: {error_message}")
            db_client.update_url(url_id, {
                "status_download": "failed",
                "status": "processing_failed",
                "last_error_details": error_message
            })
            return # 下載失敗，終止流程

        log.info(f"LINE 工作流 [ID: {url_id}]: 下載成功，檔案位於: {local_path}")
        db_client.update_url(url_id, {
            "status_download": "success",
            "local_path": local_path # 將本地路徑存回資料庫
        })

        # --- 步驟 2: 提取 ---
        db_client.update_url(url_id, {"status_extraction": "processing"})

        file_path = Path(local_path)
        image_output_dir = file_path.parent / f"extracted_images_{url_id}"

        content_data = extract_content(str(file_path), str(image_output_dir))

        text_content = content_data.get("text", "") if content_data else ""
        image_paths_json = json.dumps(content_data.get("image_paths", [])) if content_data else "[]"

        # 最終的資料庫更新 payload
        update_payload = {
            "status_extraction": "success",
            "extracted_text": text_content,
            "extracted_image_paths": image_paths_json,
        }

        if not text_content and not json.loads(image_paths_json):
            update_payload["status"] = "processed_unsupported"
            update_payload["last_error_details"] = "檔案類型不受支援或內容為空。"
        else:
            update_payload["status"] = "processed"
            update_payload["last_error_details"] = None # 清除舊的錯誤訊息

        log.info(f"LINE 工作流 [ID: {url_id}]: 提取完成，準備將結果寫入資料庫。")
        db_client.update_url(url_id, update_payload)

        log.info(f"✅ LINE 工作流 [ID: {url_id}]: 處理成功。")

    except Exception as e:
        log.error(f"LINE 工作流 [ID: {url_id}]: 發生未預期的嚴重錯誤: {e}", exc_info=True)
        # 發生未知錯誤時，將主狀態標記為失敗
        db_client.update_url(url_id, {
            "status": "processing_failed",
            "last_error_details": f"工作流發生嚴重錯誤: {str(e)}"
        })
    finally:
        # --- 步驟 3: 發送通知 (無論成功或失敗) ---
        final_record = db_client.get_url_by_id(url_id)
        if queue and loop and final_record:
            notification_msg = {
                "type": "line_item_update",
                "item_id": str(url_id),
                "status": final_record.get("status"),
                "details": {
                    "download": final_record.get("status_download"),
                    "extraction": final_record.get("status_extraction"),
                }
            }
            asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)
            log.info(f"LINE 工作流 [ID: {url_id}]: 已發送處理完成通知至佇列。")


async def run_task_wrapper(task_id: int, semaphore: asyncio.Semaphore, blocking_func, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, **kwargs):
    """
    一個通用的非同步包裝函式，用於控制併發並執行阻塞的任務。
    (從 page3_processor.py 複製而來，保持不變)
    """
    async with semaphore:
        log.info(f"任務 {task_id} 已取得信號量，準備執行...")
        try:
            # functools.partial 允許我們預先綁定 blocking_func 所需的參數
            partial_func = functools.partial(blocking_func, url_id=task_id, queue=queue, loop=loop, **kwargs)
            # run_in_executor 會在一個單獨的執行緒中執行我們的阻塞函式，從而避免阻塞事件循環
            await loop.run_in_executor(None, partial_func)
        except Exception as e:
            log.error(f"包裝函式捕獲到未預期的錯誤 (任務 {task_id}): {e}", exc_info=True)
        finally:
            log.info(f"任務 {task_id} 執行完畢，釋放信號量。")
