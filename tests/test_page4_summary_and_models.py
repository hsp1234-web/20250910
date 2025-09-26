# tests/test_page4_summary_and_models.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, ANY

# 根據專案結構調整路徑
import sys
from pathlib import Path
SRC_PATH = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_PATH))

import asyncio
from db.client import DBClient

# 延遲匯入 app，以確保路徑已設定
from api.api_server import app
from api.dependencies import get_db

@pytest.fixture
def client_and_db():
    """
    提供一個 TestClient 和一個與之關聯的、可配置的模擬資料庫實例。
    FastAPI 的 TestClient 會自動處理 lifespan 事件，因此 semaphore 和 queue 會被自動建立。
    """
    mock_db = MagicMock(spec=DBClient)
    app.dependency_overrides[get_db] = lambda: mock_db

    with TestClient(app) as client:
        yield client, mock_db # Yield both client and the mock

    app.dependency_overrides = {} # Cleanup

# --- 測試「重點摘要」頁面的檔案列表 API ---

@pytest.mark.timeout(130)
def test_get_files_for_summary_page_success(client_and_db):
    """測試成功獲取待摘要檔案列表。"""
    client, mock_db = client_and_db
    mock_files = [
        {'id': 1, 'local_path': '/files/test1.txt', 'title': '測試檔案一', 'author': '作者A', 'message_date': '2023-01-01'},
        {'id': 2, 'local_path': '/files/test2.txt', 'title': '測試檔案二', 'author': '作者B', 'message_date': '2023-01-02'}
    ]
    mock_db.get_urls_by_statuses.return_value = mock_files
    mock_db.create_or_get_analysis_task.side_effect = lambda file_id, filename: {
        'id': file_id, 'file_id': file_id, 'filename': filename, 'summary_status': 'pending'
    }

    response = client.get("/api/analyzer/files_for_summary")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]['title'] == '測試檔案一'
    assert data[1]['id'] == 2
    mock_db.get_urls_by_statuses.assert_called_once_with(statuses=['processed', 'processing_failed'])

@pytest.mark.timeout(130)
def test_get_files_for_summary_page_no_files(client_and_db):
    """測試沒有可供摘要的檔案時的情況。"""
    client, mock_db = client_and_db
    mock_db.get_urls_by_statuses.return_value = []

    response = client.get("/api/analyzer/files_for_summary")

    assert response.status_code == 200
    assert response.json() == []

# --- 測試模型列表 API ---

@pytest.mark.timeout(130)
@patch('api.routes.page6_keys.key_manager')
@patch('tools.gemini_manager.GeminiManager') # JULES FIX: Patch the correct import path
def test_get_available_models_success(mock_gemini_manager, mock_key_manager, client_and_db):
    """測試成功獲取模型列表。"""
    client, _ = client_and_db
    mock_key_manager.get_all_valid_keys_for_manager.return_value = [{'key': 'valid_key'}]
    mock_gemini_instance = mock_gemini_manager.return_value
    mock_gemini_instance.list_available_models.return_value = ['models/gemini-1.5-pro', 'models/gemini-1.5-flash']

    response = client.get("/api/keys/models")

    assert response.status_code == 200
    assert response.json() == ['models/gemini-1.5-pro', 'models/gemini-1.5-flash']

@pytest.mark.timeout(130)
@patch('api.routes.page6_keys.key_manager')
def test_get_available_models_no_valid_keys(mock_key_manager, client_and_db):
    """測試沒有有效金鑰時，無法獲取模型列表。"""
    client, _ = client_and_db
    mock_key_manager.get_all_valid_keys_for_manager.return_value = []

    response = client.get("/api/keys/models")

    assert response.status_code == 400
    assert "沒有可用的有效 API 金鑰" in response.json()['detail']

# --- 測試啟動重點摘要生成 API ---

@pytest.mark.timeout(130)
@patch('api.routes.page4_analyzer.run_analysis_task_wrapper')
def test_start_summary_generation_success(mock_run_wrapper, client_and_db):
    """測試成功啟動重點摘要生成任務。"""
    client, mock_db = client_and_db

    with patch('asyncio.get_running_loop'):
        response = client.post(
            "/api/analyzer/start_summary_generation",
            json={"task_ids": [1, 2], "model_name": "gemini-1.5-flash"}
        )

    assert response.status_code == 200
    assert "已成功為 2 個任務啟動重點摘要生成" in response.json()['message']

    assert mock_db.update_analysis_task.call_count == 2
    mock_db.update_analysis_task.assert_any_call(task_id=1, updates={
        "summary_status": "pending", "summary_content": None, "summary_error_log": None,
        "summary_token_usage": None, "summary_model": None
    })

    assert mock_run_wrapper.call_count == 2
    mock_run_wrapper.assert_any_call(
        task_id=1,
        semaphore=ANY,
        blocking_func=ANY,
        queue=ANY,
        loop=ANY,
        db_client=mock_db,
        model_name="gemini-1.5-flash",
        stage="summary"
    )

@pytest.mark.timeout(130)
def test_start_summary_generation_no_ids(client_and_db):
    """測試請求中沒有提供任務 ID 的情況。"""
    client, _ = client_and_db
    response = client.post(
        "/api/analyzer/start_summary_generation",
        json={"task_ids": [], "model_name": "gemini-1.5-flash"}
    )
    assert response.status_code == 400
    assert "任務 ID 列表不可為空" in response.json()['detail']
