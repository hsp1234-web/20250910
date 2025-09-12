import pytest
import sys
import os
import json
import time
from pathlib import Path

# --- 測試環境路徑設定 ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# --- 匯入待測試的模組 ---
from db.database import get_db_connection, initialize_database, set_app_state
from core import key_manager
from tools import url_extractor, drive_downloader
from api.routes.page3_processor import run_processing_task
from api.routes.page4_analyzer import run_ai_analysis_task

# --- 常數 ---
# 從環境變數讀取真實 API 金鑰
E2E_API_KEY_1 = os.environ.get("E2E_GEMINI_KEY_1")
E2E_API_KEY_2 = os.environ.get("E2E_GEMINI_KEY_2")

# 建立一個包含有效金鑰的列表
REAL_API_KEYS = []
if E2E_API_KEY_1:
    REAL_API_KEYS.append({"name": "e2e_key_1", "value": E2E_API_KEY_1})
if E2E_API_KEY_2:
    REAL_API_KEYS.append({"name": "e2e_key_2", "value": E2E_API_KEY_2})

# 如果沒有設定任何金鑰，則跳過此測試模組
pytestmark = pytest.mark.skipif(
    not REAL_API_KEYS,
    reason="需要設定 E2E_GEMINI_KEY_1 和/或 E2E_GEMINI_KEY_2 環境變數才能執行端對端測試。"
)


CHAT_LOG_INPUT = """
17:46	504-0718103Leo	四月小作文-精確3162
https://docs.google.com/document/d/16TkL54YmFAToS1UR26VdV_mYgr8bCAml/edit?tab=t.0
17:48	505-0724540捲髮狼	四月小作文-5515建國
https://drive.google.com/file/d/1dwnVczcEvhIIj5TOXRHVow876da6zAGp/view?usp=drivesdk
2025/4/5（週六）
12:21	383-0488695 三寶	小作文-2424隴華
https://docs.google.com/document/d/10nDGa7nWuSZCLhU9qtR_VW8Cx-yQllk5/edit?usp=drive_link&ouid=105443695704290227678&rtpof=true&sd=true
13:19	421-0299033青蛙狼	https://docs.google.com/document/d/1-OeWOZfZ8-KQb2-S-QhfthC7k-UPb4KofyzmLiGT17Y/edit
14:09	503-0551726千千	四月小作文-日月光投控 3711
https://drive.google.com/file/d/1ADg9NnB10z3qjnSZPOn6BLh_Fz8wjY9T/view?usp=sharing
"""

@pytest.mark.e2e
class TestRealDataE2E:

    def setup_method(self):
        """在每個測試方法前執行，用於設定環境"""
        # 清理舊金鑰
        key_manager._save_keys([])

        # 使用 API 新增真實金鑰
        for key_data in REAL_API_KEYS:
            try:
                key_manager.add_key(key_data['value'], key_data['name'])
                print(f"成功新增金鑰: {key_data['name']}")
            except ValueError as e:
                # 如果金鑰已存在 (在同一個測試執行中可能發生)，則忽略
                print(f"新增金鑰 {key_data['name']} 時發生錯誤 (可能已存在): {e}")
                pass

        # 設定一個假的伺服器埠號，以避免 WebSocket 通知失敗
        # 注意：在測試環境中，這可能需要一個更穩健的 mock，但對於 CLI 測試是可行的
        set_app_state('server_port', '8001')


    def teardown_method(self):
        """在每個測試方法後執行，用於清理"""
        # 清理金鑰檔案
        keys_file = SRC_DIR / "db" / "secrets" / "keys.json"
        if keys_file.exists():
            os.remove(keys_file)

    def test_full_backend_pipeline_with_real_data(self, db_conn, tmp_path):
        """
        使用真實資料測試從網址提取到 AI 分析的完整後端流程。
        注意：此測試會發起真實的網路請求。
        """
        # --- 1. 網址提取 ---
        print("\n--- (1/5) 開始網址提取 ---")
        extracted_results = url_extractor.parse_chat_log(CHAT_LOG_INPUT)
        url_extractor.save_urls_to_db(extracted_results, CHAT_LOG_INPUT, db_conn)

        cursor = db_conn.cursor()
        # 提取所有需要的欄位以供下載器使用
        cursor.execute("SELECT id, url, author, message_date, message_time FROM extracted_urls WHERE status = 'pending'")
        pending_urls = cursor.fetchall()

        assert len(pending_urls) == 5, f"預期提取 5 個網址，但實際提取了 {len(pending_urls)} 個"
        print(f"✅ 成功提取並儲存 {len(pending_urls)} 個網址。")

        # --- 2. 檔案下載 ---
        print("\n--- (2/5) 開始檔案下載 ---")
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()

        downloaded_ids = []
        for row in pending_urls:
            print(f"  正在下載: {row['url']}")
            try:
                final_path = drive_downloader.download_file(
                    url=row['url'],
                    output_dir=str(download_dir),
                    url_id=row['id'],
                    author=row['author'],
                    message_date=row['message_date'],
                    message_time=row['message_time']
                )
                if final_path:
                    # 更新資料庫中的 local_path 和狀態
                    cursor.execute(
                        "UPDATE extracted_urls SET local_path = ?, status = 'completed' WHERE id = ?",
                        (final_path, row['id'])
                    )
                    db_conn.commit()
                    print(f"  ✅ 下載成功: {final_path}")
                    downloaded_ids.append(row['id'])
                else:
                    print(f"  ⚠️ 下載失敗或跳過: {row['url']}")
            except Exception as e:
                print(f"  ❌ 下載時發生錯誤: {row['url']} - {e}")

        assert len(downloaded_ids) > 0, "至少應成功下載一個檔案才能繼續測試"
        print(f"✅ 成功下載 {len(downloaded_ids)} 個檔案。")

        # --- 3. 內容處理 ---
        print("\n--- (3/5) 開始內容處理 ---")
        processed_ids = []
        for file_id in downloaded_ids:
            print(f"  正在處理檔案 ID: {file_id}")
            run_processing_task(file_id, port=0)
            processed_ids.append(file_id)

        cursor.execute(f"SELECT COUNT(*) FROM extracted_urls WHERE id IN ({','.join('?' for _ in processed_ids)}) AND status = 'processed'", processed_ids)
        processed_count = cursor.fetchone()[0]
        assert processed_count == len(processed_ids), "所有已處理的檔案狀態都應更新為 'processed'"
        print(f"✅ 成功處理 {processed_count} 個檔案。")

        # --- 4. AI 分析 ---
        print("\n--- (4/5) 開始 AI 分析 (將發起真實 API 請求) ---")
        # 在分析前，確保測試用的提示詞存在
        from core import prompt_manager
        prompts_to_save = {
            "stage_1_extraction_prompt": "請從以下文字提取結構化資料：{document_text}",
            "stage_2_generation_prompt": "請根據以下資料生成報告：{data_package}"
        }
        prompt_manager.save_prompts(prompts_to_save)
        run_ai_analysis_task(processed_ids, server_port=0)

        # --- 5. 結果驗證 ---
        print("\n--- (5/5) 等待並驗證最終結果 ---")
        timeout = 300
        start_time = time.time()
        all_done = False
        while time.time() - start_time < timeout:
            cursor.execute(f"SELECT status FROM extracted_urls WHERE id IN ({','.join('?' for _ in processed_ids)})", processed_ids)
            statuses = [row['status'] for row in cursor.fetchall()]
            print(f"  目前狀態: {statuses}")

            if all(s in ['analyzed', 'error', 'pending_retry'] for s in statuses):
                all_done = True
                break
            time.sleep(15)

        assert all_done, f"在 {timeout} 秒後，分析仍未全部完成。"

        cursor.execute(f"SELECT id, status, status_message FROM extracted_urls WHERE id IN ({','.join('?' for _ in processed_ids)})", processed_ids)
        final_results = cursor.fetchall()

        success_count = sum(1 for row in final_results if row['status'] == 'analyzed')

        print("\n--- 測試結果 ---")
        for row in final_results:
            print(f"  - 檔案 ID {row['id']}: 最終狀態='{row['status']}', 訊息='{row['status_message']}'")

        assert success_count > 0, "端對端測試應至少成功分析一個檔案"
        print(f"✅ 端對端測試成功，完成分析 {success_count}/{len(processed_ids)} 個檔案。")
