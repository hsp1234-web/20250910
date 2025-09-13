# tests/test_stage1_analysis.py
import pytest
import json
import sys
from pathlib import Path
import time
import os

# --- 測試環境路徑設定 ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# --- 匯入被測試的模組 ---
from core import key_manager
from db.client import get_client
from api.routes.page4_analyzer import run_stage1_task

# --- 常數 ---
# 使用者提供的 API 金鑰
USER_API_KEY = "AIzaSyCR4gdpWDk9evli0iULcfkiOinL_vKdFnU"
# 使用者指定的模型，使用一個標準的名稱
MODEL_NAME = "gemini-1.5-flash-latest"

@pytest.fixture(scope="module", autouse=True)
def setup_api_key():
    """在所有測試開始前，自動新增一次 API 金鑰。"""
    # 這是為了確保即使在 CI/CD 環境中，金鑰檔案也是存在的
    # 在本地端，這通常只會執行一次
    keys = key_manager._load_keys()
    key_hash = key_manager._hash_key(USER_API_KEY)

    if any(k["key_hash"] == key_hash for k in keys):
        print("API 金鑰已存在，跳過新增。")
        return

    try:
        print(f"正在新增用於測試的 API 金鑰: {USER_API_KEY[:10]}...")
        # 注意：這會觸發一個真實的 API 驗證呼叫
        key_manager.add_key(USER_API_KEY, "test_key_for_stage1")
        print("API 金鑰新增成功。")
    except ValueError as e:
        if "此 API 金鑰已存在" in str(e):
            print("API 金鑰已存在 (競態條件)，繼續測試。")
            pass
        else:
            pytest.fail(f"新增 API 金鑰失敗: {e}")
    except Exception as e:
        pytest.fail(f"新增 API 金鑰時發生未預期錯誤，請檢查網路連線與金鑰有效性: {e}")


def test_stage1_analysis_produces_correct_json(db_conn, tmp_path):
    """
    整合測試：驗證 run_stage1_task 是否能根據給定的文字和新的提示詞，
    成功生成一個包含 title, sentiment, 和 symbol 的結構化 JSON。
    """
    # 1. 準備測試資料
    mock_article_text = """
    標題：台積電(TSM)前景看好，長期投資價值浮現

    我個人非常看多台積電(TSM)的未來發展。
    從幾個方面來看，首先，AI晶片的需求持續火爆，台積電作為行業龍頭，其先進製程無可替代。
    其次，公司的全球佈局和客戶關係非常穩固。
    雖然短期可能有一些庫存調整的波動，但長期來看，公司的成長趨勢明確。
    因此，我認為現在是佈局的好時機。
    """
    mock_file_id = 1
    mock_author = "Test Author"
    mock_url = "http://mock.url/doc1"
    mock_filename = "mock_tsm_article.txt"

    # 2. 設定測試環境 (寫入資料庫)
    # 使用 db_conn fixture 來直接操作測試資料庫
    cursor = db_conn.cursor()
    cursor.execute(
        "INSERT INTO extracted_urls (id, author, url, source_text) VALUES (?, ?, ?, ?)",
        (mock_file_id, mock_author, mock_url, mock_article_text)
    )
    db_conn.commit()

    # 使用 DBClient 來建立分析任務 (這是應用程式的正常流程)
    # 注意：在測試中，DBClient 會自動使用被 monkeypatch 的測試資料庫路徑
    db_client = get_client()
    task = db_client.create_or_get_analysis_task(file_id=mock_file_id, filename=mock_filename)
    assert task is not None, "無法建立分析任務"
    task_id = task['id']

    # 3. 執行被測試的函式
    # 我們需要一個假的 server_port
    mock_server_port = 50000
    run_stage1_task(task_id=task_id, file_id=mock_file_id, model_name=MODEL_NAME, server_port=mock_server_port)

    # 4. 驗證結果
    # 從資料庫中獲取任務的最終狀態和 JSON 檔案路徑
    # 等待一小段時間確保檔案系統操作完成
    time.sleep(1)
    updated_task = db_client.get_analysis_task(task_id)

    assert updated_task is not None, "在資料庫中找不到更新後的任務"
    assert updated_task['stage1_status'] == 'completed', f"第一階段任務失敗: {updated_task['stage1_error_log']}"
    assert updated_task['stage1_json_path'] is not None, "資料庫中未記錄 JSON 檔案路徑"

    # 讀取產出的 JSON 檔案
    # 確保路徑是絕對路徑或相對於一個已知的基準
    json_path = Path(updated_task['stage1_json_path'])
    if not json_path.is_absolute():
        # 假設路徑是相對於專案根目錄
        json_path = SRC_DIR.parent / json_path

    assert json_path.exists(), f"產出的 JSON 檔案不存在於預期路徑：{json_path}"

    with open(json_path, "r", encoding="utf-8") as f:
        result_data = json.load(f)

    # 驗證 JSON 結構和內容
    assert "title" in result_data, "結果中缺少 'title' 欄位"
    assert "sentiment" in result_data, "結果中缺少 'sentiment' 欄位"
    assert "symbol" in result_data, "結果中缺少 'symbol' 欄位"

    assert "台積電" in result_data["title"], f"標題內容不符預期: {result_data['title']}"
    assert result_data["sentiment"] == "看多", f"情感判斷不符預期: {result_data['sentiment']}"
    assert result_data["symbol"].upper() == "TSM", f"股票代號不符預期: {result_data['symbol']}"

    print(f"\n✅ 測試成功！產出的 JSON 結構與內容符合預期。")
    print(f"產出內容: {json.dumps(result_data, ensure_ascii=False, indent=2)}")
