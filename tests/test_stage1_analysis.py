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
import asyncio
from core import key_manager
# from db.client import get_client # JULES: Replaced with direct db_conn access
from api.routes.page4_analyzer import _run_stage1_blocking_task

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


def test_stage1_analysis_produces_correct_json(db_conn, tmp_path, monkeypatch):
    """
    整合測試：驗證 run_stage1_task 是否能根據給定的文字和新的提示詞，
    成功生成一個包含 title, sentiment, 和 symbol 的結構化 JSON。
    """
    # JULES (2025-09-14): 建立一個 FakeDBClient 並使用 monkeypatch 替換
    # page4_analyzer 中的全域 DB_CLIENT，以解決 ConnectionRefusedError。
    class FakeDBClient:
        def __init__(self, conn):
            self._conn = conn

        def get_analysis_task(self, task_id):
            cursor = self._conn.cursor()
            sql = "SELECT * FROM analysis_tasks WHERE id = ?"
            cursor.execute(sql, (task_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

        def get_url_by_id(self, url_id):
            cursor = self._conn.cursor()
            sql = "SELECT * FROM extracted_urls WHERE id = ?"
            cursor.execute(sql, (url_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

        def update_analysis_task(self, task_id, updates):
            set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
            values = list(updates.values()) + [task_id]
            sql = f"UPDATE analysis_tasks SET {set_clause} WHERE id = ?"
            cursor = self._conn.cursor()
            cursor.execute(sql, values)
            self._conn.commit()
            return True

    monkeypatch.setattr(
        "api.routes.page4_analyzer.DB_CLIENT",
        FakeDBClient(db_conn)
    )
    monkeypatch.setattr(
        "api.routes.page4_analyzer.key_manager",
        key_manager
    )

    # JULES (2025-09-14): 修正 - 注入一個有效的 API 金鑰以進行測試
    # 為了避免真實的網路呼叫，我們模擬驗證函式使其永遠成功
    monkeypatch.setattr("core.key_manager._validate_single_key", lambda key: True)
    # 使用者提供的金鑰
    USER_API_KEY = "AIzaSyBdw0gY2oh2W_r1eN3ALzK9RCAAcedgF3E"
    try:
        key_manager.add_key(USER_API_KEY, "test_key_for_analysis")
    except ValueError:
        pass # 金鑰可能已在先前的測試中被加入，忽略重複錯誤

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

        # JULES (2025-09-14): 修正 - 將待分析的文字直接插入 analysis_tasks 表，以模擬真實流程
    cursor.execute(
            "INSERT INTO analysis_tasks (file_id, filename, stage1_status, file_content_for_analysis) VALUES (?, ?, ?, ?)",
            (mock_file_id, mock_filename, 'pending', mock_article_text)
    )
    db_conn.commit()
    task_id = cursor.lastrowid
    assert task_id is not None, "無法建立分析任務"

    # 3. 執行被測試的函式
    # JULES (2025-09-14): 為了適應重構後的架構，我們現在直接測試核心的阻塞函式。
    # 為此，我們需要建立一個模擬的佇列和一個事件迴圈來滿足函式的簽章需求。
    mock_queue = asyncio.Queue()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # 'RuntimeError: There is no current event loop...'
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # 呼叫重構後的核心邏輯函式
    _run_stage1_blocking_task(task_id=task_id, file_id=mock_file_id, model_name=MODEL_NAME, queue=mock_queue, loop=loop)


    # 4. 驗證結果
    # 從資料庫中獲取任務的最終狀態和 JSON 檔案路徑
    # 等待一小段時間確保檔案系統操作完成
    time.sleep(1)
    cursor.execute("SELECT * FROM analysis_tasks WHERE id = ?", (task_id,))
    updated_task = cursor.fetchone()

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
