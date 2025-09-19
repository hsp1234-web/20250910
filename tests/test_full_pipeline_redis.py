import pytest
import redis
import fakeredis
import json
import uuid
import threading
import time
import sys
from pathlib import Path

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

# 服務模組
from services import processor_service
from services import analyzer_service
# 資料庫客戶端
from db.client import DBClient


@pytest.fixture(scope="module")
def fake_redis_client():
    """提供一個模組級別的 FakeRedis 客戶端實例。"""
    # 使用 fakeredis.aioredis 是為了相容可能存在的非同步代碼，儘管我們這裡主要是同步使用
    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=True)
    return client


@pytest.fixture(scope="module")
def test_services(monkeymodule, fake_redis_client):
    """
    一個模組級別的 fixture，用於啟動我們的微服務監聽器。
    - 使用 `monkeymodule` (pytest 的一個功能) 來修補 redis.Redis，使其在整個模組中都使用我們的假客戶端。
    - 在背景執行緒中啟動 processor 和 analyzer 服務。
    """
    # 修補 redis.Redis，讓所有服務都使用我們的 fake_redis_client
    monkeymodule.setattr(redis, 'Redis', lambda **kwargs: fake_redis_client)

    # 建立並啟動 processor 服務的監聽執行緒
    processor_thread = threading.Thread(
        target=processor_service.start_redis_processor_listener,
        daemon=True
    )
    processor_thread.start()

    # 建立並啟動 analyzer 服務的監聽執行緒
    analyzer_thread = threading.Thread(
        target=analyzer_service.start_redis_analyzer_listener,
        daemon=True
    )
    analyzer_thread.start()

    # 測試執行時，服務已在背景運行
    yield fake_redis_client

    # 清理 (雖然 daemon 執行緒會隨主程序退出，但這是一個好的實踐)
    # 在這個簡單的測試中，我們不實現複雜的執行緒停止機制
    print("測試模組完成，背景服務將隨之退出。")


def test_full_pipeline_with_fakeredis(test_services, tmp_path):
    """
    端到端整合測試，驗證從下載完成到分析完成的完整 Redis 工作流。
    """
    # --- 1. Arrange (準備階段) ---

    # 獲取由 fixture 提供的假 Redis 客戶端
    redis_client = test_services
    db_client = DBClient()

    # 建立一個假的下載檔案
    dummy_content = "這是一份關於台積電 (2330) 的研究報告..."
    dummy_file = tmp_path / "dummy_report.txt"
    dummy_file.write_text(dummy_content, encoding="utf-8")

    # 產生一個唯一的任務 ID
    task_id = str(uuid.uuid4())

    # 在資料庫中建立一個初始任務記錄，模擬 downloader 完成後的情境
    # 注意：在真實流程中，downloader 會先建立這個任務
    initial_payload = {
        "url": f"mock://{dummy_file.name}",
        "title": dummy_file.name,
    }
    db_client.add_task(task_id, json.dumps(initial_payload), task_type='download', status='download_complete')

    # 準備要發布到 Redis 的初始訊息 (由 downloader 發布)
    download_complete_message = {
        "task_id": task_id,
        "timestamp": time.time(),
        "source_service": "downloader_service",
        "status": "success",
        "payload": {
            "file_path": str(dummy_file),
            "original_filename": dummy_file.name
        }
    }

    # --- 2. Act (執行階段) ---

    # 將 "下載完成" 訊息發布到 Redis，觸發 processor_service
    redis_client.publish(
        processor_service.DOWNLOAD_COMPLETE_CHANNEL,
        json.dumps(download_complete_message)
    )

    # --- 3. Assert (斷言階段) ---

    # 等待分析完成。因為服務在背景執行緒中運行，我們需要輪詢資料庫來檢查最終狀態。
    final_status = None
    timeout_seconds = 20  # 設定一個合理的超時時間
    start_time = time.time()

    print(f"\n[測試] 等待任務 {task_id} 完成...")
    while time.time() - start_time < timeout_seconds:
        task_record = db_client.get_task_status(task_id)
        current_status = task_record.get("status")

        print(f"[測試] ...目前狀態: {current_status}")

        if current_status in ["analysis_complete", "analysis_failed"]:
            final_status = current_status
            break

        time.sleep(1) # 每次檢查之間等待 1 秒

    # 斷言最終狀態是否為 'analysis_complete'
    assert final_status == "analysis_complete", f"任務處理超時或失敗，最終狀態為: {final_status}"

    # (可選) 檢查更詳細的結果
    final_task_record = db_client.get_task_status(task_id)
    final_result = json.loads(final_task_record.get("result", "{}"))

    # 斷言分析結果已附加到主任務記錄中
    assert "analysis_json_path" in final_result, "最終結果中應包含分析產生的 JSON 路徑"
    assert final_result.get("validated_symbol") == "2330.TW", "最終結果中應包含驗證後的股票代號"

    # 讀取分析產生的 JSON 檔案並驗證其內容
    analysis_json_path = Path(final_result["analysis_json_path"])
    assert analysis_json_path.exists(), "分析產生的 JSON 檔案應存在於指定路徑"

    with open(analysis_json_path, "r", encoding="utf-8") as f:
        analysis_data = json.load(f)

    assert analysis_data.get("symbol") == "2330.TW", "JSON 檔案中的股票代號應為 '2330.TW'"

    print(f"[測試] 任務 {task_id} 成功完成端到端流程！🎉")
