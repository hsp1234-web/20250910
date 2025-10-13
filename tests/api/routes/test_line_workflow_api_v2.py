import pytest
from fastapi.testclient import TestClient
import json

# 專案內部模組匯入
from src.api.api_server import app
from src.db.database import get_db_connection, initialize_database

# --- 測試用的 Fixtures ---

@pytest.fixture(scope="function")
def test_db(monkeypatch):
    """
    一個 fixture，為每個測試函式建立一個乾淨的、基於記憶體的資料庫。
    並在測試結束後清理。
    """
    # 使用 monkeypatch 來設定環境變數，讓 get_db_connection 使用記憶體資料庫
    monkeypatch.setenv("TEST_DB_PATH", ":memory:")

    conn = get_db_connection()
    initialize_database(conn)

    yield conn

    conn.close()

@pytest.fixture(scope="function")
def client(test_db):
    """
    一個 fixture，提供一個 FastAPI TestClient，並將其與測試資料庫關聯。
    """
    # 覆寫應用程式的 get_db_connection 依賴，使其使用我們的測試資料庫
    def override_get_db_connection():
        return test_db

    app.dependency_overrides[get_db_connection] = override_get_db_connection

    with TestClient(app) as c:
        yield c

    # 清除覆寫，避免影響其他測試
    app.dependency_overrides = {}


# --- 測試案例 ---

def test_get_workflow_status_success(client: TestClient, mocker):
    """
    測試 /api/workflows/{workflow_id}/status 端點是否能成功運作。
    (Jules @ 2025-10-14) 已更新為使用 mocker 來模擬 DBClient，避免實際的 HTTP 請求。
    """
    # 1. 準備模擬資料
    mock_workflow = {'id': 1, 'name': 'Test Workflow', 'status': 'running'}
    mock_steps = [{
        'id': 1,
        'workflow_id': 1,
        'step_order': 1,
        'command': 'DOWNLOAD_AND_EXTRACT',
        'parameters': {'source_url_id': 101},
        'status': 'completed'
    }]
    mock_item_details = {
        'id': 101,
        'url': 'http://test.com/1',
        'author': 'author1',
        'status': 'downloaded',
        'status_download': 'success',
        'status_extraction': 'success',
        'status_ocr': 'not_applicable',
        'status_ai_summary': 'pending',
        'last_error_details': None
    }

    # 2. 設定模擬
    # 模擬 DBClient 的實例方法
    mocker.patch('db.client.DBClient.get_workflow', return_value=mock_workflow)
    mocker.patch('db.client.DBClient.get_workflow_steps', return_value=mock_steps)
    mocker.patch('db.client.DBClient.get_url_by_id', return_value=mock_item_details)

    # 3. 執行 API 請求
    response = client.get("/api/workflows/1/status")

    # 4. 斷言結果
    assert response.status_code == 200
    data = response.json()

    # 驗證回傳的結構和內容
    assert data['workflow_id'] == 1
    assert data['workflow_status'] == 'running'
    assert len(data['steps']) == 1

    step_status = data['steps'][0]
    assert step_status['step_id'] == 1
    assert step_status['source_url_id'] == 101
    assert step_status['overall_status'] == 'downloaded'
    assert step_status['status_download'] == 'success'