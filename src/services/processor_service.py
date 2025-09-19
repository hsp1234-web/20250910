import redis
import json
import logging
import sys
import threading
import time
from pathlib import Path
import datetime

# --- 路徑修正與模組匯入 ---
# 確保能夠找到 src 下的模組
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from db.client import DBClient
from tools.content_extractor import extract_content
from tools.file_hasher import calculate_sha256

# --- 設定 ---
log = logging.getLogger(__name__)
# JULES: 這裡我們建立一個獨立的 DBClient 實例，因為此服務可能在獨立進程中運行。
# 在當前架構下，它與 API 伺服器共享進程，但這樣設計更具未來擴展性。
db_client = DBClient()

# --- Redis 連線設定 ---
# JULES: 從環境變數讀取 Redis 主機和埠號，提供預設值以便本地開發。
# 這使得設定更加靈活，方便在不同環境中部署。
REDIS_HOST = "localhost"
REDIS_PORT = 6379
DOWNLOAD_COMPLETE_CHANNEL = "tasks:download_complete"
PROCESSING_COMPLETE_CHANNEL = "tasks:processing_complete"


def process_file_from_message(message_data: dict):
    """
    根據從 Redis 收到的訊息處理單一檔案。
    這是取代舊版 _run_processing_blocking_task 的核心邏輯。
    """
    task_id = message_data.get("task_id")
    payload = message_data.get("payload", {})
    file_path_str = payload.get("file_path")
    original_filename = payload.get("original_filename")

    if not all([task_id, file_path_str, original_filename]):
        log.error(f"[Processor] 訊息格式錯誤，缺少必要欄位: {message_data}")
        return

    log.info(f"[Processor] 開始處理任務 {task_id}，檔案: {file_path_str}")
    db_client.update_task_status(task_id, "processing", {"detail": "內容提取中..."})

    try:
        file_path = Path(file_path_str)
        if not file_path.is_file():
            raise FileNotFoundError(f"檔案系統中找不到檔案: {file_path}")

        # 1. 計算檔案雜湊值
        file_hash = calculate_sha256(file_path)

        # 2. 提取內容 (文字與圖片)
        image_output_dir = file_path.parent / "extracted_images"
        content_data = extract_content(str(file_path), str(image_output_dir))

        text_content = content_data.get("text", "")
        image_paths = content_data.get("image_paths", [])

        # 3. 判斷處理結果
        if not text_content and not image_paths:
            status = 'processed_unsupported'
            status_message = '不支援的檔案類型或檔案為空，無法提取任何內容。'
        else:
            status = 'processed'
            status_message = '處理成功'

        # 4. 準備要更新到資料庫的結果
        result_payload = {
            "file_hash": file_hash,
            "extracted_text": text_content,
            "extracted_image_paths": image_paths,
            "original_filename": original_filename,
            "detail": status_message
        }
        db_client.update_task_status(task_id, status, result_payload)
        log.info(f"[Processor] 任務 {task_id} 處理成功，狀態: {status}")

        # 5. 發布新訊息到下一個頻道
        publish_processing_complete(task_id, status, payload, result_payload)

    except Exception as e:
        error_message = f"處理任務 {task_id} 時發生嚴重錯誤: {e}"
        log.error(error_message, exc_info=True)
        db_client.update_task_status(task_id, "processing_failed", {"error": error_message})


def publish_processing_complete(task_id: str, status: str, original_payload: dict, processing_result: dict):
    """
    將處理完成的訊息發布到 Redis。
    """
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

    # 合併原始 payload 和新的處理結果
    new_payload = {**original_payload, **processing_result}

    message = {
        "task_id": task_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_service": "processor_service",
        "status": "success" if status in ["processed", "processed_unsupported"] else "failure",
        "payload": new_payload
    }

    try:
        redis_client.publish(PROCESSING_COMPLETE_CHANNEL, json.dumps(message))
        log.info(f"[Processor] 已將任務 {task_id} 的處理完成訊息發布至頻道 '{PROCESSING_COMPLETE_CHANNEL}'")
    except Exception as e:
        log.error(f"[Processor] 發布訊息至 Redis 時失敗: {e}", exc_info=True)


def start_redis_processor_listener():
    """
    啟動 Redis 監聽器，在一個單獨的執行緒中運行。
    """
    log.info("[Processor] 啟動 Redis 監聽器，準備接收下載完成的任務...")

    # JULES: 每個執行緒都應該有自己的 Redis 連線實例
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
    pubsub = redis_client.pubsub()
    pubsub.subscribe(DOWNLOAD_COMPLETE_CHANNEL)

    log.info(f"[Processor] 已訂閱頻道: {DOWNLOAD_COMPLETE_CHANNEL}")

    for message in pubsub.listen():
        if message['type'] == 'message':
            log.info(f"[Processor] 從 Redis 收到新訊息！")
            try:
                message_data = json.loads(message['data'])
                log.debug(f"訊息內容: {message_data}")
                # 每次收到訊息都啟動一個新的執行緒來處理，避免阻塞主監聽迴圈
                # 這使得監聽器可以立即接收下一條訊息，而不會被當前的處理任務卡住。
                processing_thread = threading.Thread(target=process_file_from_message, args=(message_data,))
                processing_thread.start()
            except json.JSONDecodeError:
                log.error(f"[Processor] 無法解析收到的訊息: {message['data']}")
            except Exception as e:
                log.error(f"[Processor] 處理訊息時發生未預期錯誤: {e}", exc_info=True)

if __name__ == '__main__':
    # 這個區塊允許此腳本被獨立執行，方便進行單元測試或獨立部署。
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log.info("正在獨立模式下啟動處理器服務...")
    start_redis_processor_listener()
