# tests/api/routes/test_line_workflow_api.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

# --- Fixtures ---

@pytest.fixture
def mock_db_client():
    """建立一個 DBClient 的模擬實例。"""
    return MagicMock()

@pytest.fixture
def api_client(mock_db_client):
    """
    提供一個高度隔離的 TestClient。

    此 fixture 建立了一個全新的、迷你的 FastAPI 應用，
    並且只掛載了我們正在測試的 `line_workflow_api` 路由。
    這確保了測試的獨立性，避免了載入整個應用程式帶來的不必要依賴。
    """
    from src.api.routes.line_workflow_api import router as workflow_router
    from src.db.client import DBClient

    # 建立一個迷你的 FastAPI 應用實例
    app = FastAPI()

    # 只掛載我們需要測試的路由
    app.include_router(workflow_router)

    # 使用 FastAPI 的依賴覆寫功能，將 DBClient 替換為我們的模擬物件
    # (Jules @ 2025-10-15) 修正：將依賴注入綁定到 get_db_client 函數
    from src.api.routes.line_workflow_api import get_db_client
    app.dependency_overrides[get_db_client] = lambda: mock_db_client

    with TestClient(app) as client:
        yield client

    # 測試結束後清理，恢復原始的依賴
    app.dependency_overrides.clear()

# --- 測試案例 ---

# === 測試 GET /api/workflows/latest ===

def test_get_latest_workflow_success(api_client: TestClient, mock_db_client: MagicMock):
    """測試成功獲取最新工作流的情況。"""
    # 準備：設定模擬資料和模擬物件的行為
    mock_workflow = {"id": 10, "name": "最新的任務", "status": "completed"}
    mock_steps = [{"id": 1, "command": "parse"}, {"id": 2, "command": "analyze"}]
    mock_db_client.get_latest_workflow.return_value = mock_workflow
    mock_db_client.get_workflow_steps.return_value = mock_steps

    # 執行：發送請求
    response = api_client.get("/api/workflows/latest")

    # 斷言：驗證結果
    assert response.status_code == 200
    data = response.json()
    assert data["workflow"] == mock_workflow
    assert data["steps"] == mock_steps
    mock_db_client.get_latest_workflow.assert_called_once()
    mock_db_client.get_workflow_steps.assert_called_once_with(10)


def test_get_latest_workflow_not_found(api_client: TestClient, mock_db_client: MagicMock):
    """測試資料庫中沒有任何工作流的情況。"""
    # 準備：設定模擬物件的行為
    mock_db_client.get_latest_workflow.return_value = None

    # 執行：發送請求
    response = api_client.get("/api/workflows/latest")

    # 斷言：驗證結果
    assert response.status_code == 404
    assert response.json()["detail"] == "尚未建立任何工作流。"
    mock_db_client.get_latest_workflow.assert_called_once()
    mock_db_client.get_workflow_steps.assert_not_called()

# === 測試 POST /api/workflows/{workflow_id}/reset ===

def test_reset_workflow_success(api_client: TestClient, mock_db_client: MagicMock):
    """測試成功重置工作流的情況。"""
    # 準備
    workflow_id = 5
    mock_db_client.reset_workflow_status.return_value = None

    # 執行
    response = api_client.post(f"/api/workflows/{workflow_id}/reset")

    # 斷言
    assert response.status_code == 200
    assert response.json()["message"] == f"工作流 #{workflow_id} 已成功重置。"
    mock_db_client.reset_workflow_status.assert_called_once_with(workflow_id)

def test_reset_workflow_not_found(api_client: TestClient, mock_db_client: MagicMock):
    """測試試圖重置一個不存在的工作流。"""
    # 準備
    workflow_id = 999
    mock_db_client.reset_workflow_status.side_effect = ValueError(f"ID 為 {workflow_id} 的工作流不存在。")

    # 執行
    response = api_client.post(f"/api/workflows/{workflow_id}/reset")

    # 斷言
    assert response.status_code == 404
    assert response.json()["detail"] == f"ID 為 {workflow_id} 的工作流不存在。"
    mock_db_client.reset_workflow_status.assert_called_once_with(workflow_id)

# === 測試舊端點是否已移除 ===
def test_get_all_workflows_is_removed(api_client: TestClient):
    """測試 GET /api/workflows/ 端點是否已不存在。"""
    response = api_client.get("/api/workflows/")
    # 斷言：我們預期這個端點現在應該返回 404 Not Found
    assert response.status_code == 404

# === 測試 POST /api/workflows/create_from_items ===

def test_create_workflow_from_items_success(api_client: TestClient, mock_db_client: MagicMock):
    """測試從項目列表成功建立工作流。"""
    # 準備
    request_payload = {
        "name": "新任務",
        "items": [
            {"id": 1, "url": "http://example.com/1"},
            {"id": 2, "url": "http://example.com/2"}
        ]
    }
    # 模擬 DB 操作
    mock_db_client.create_workflow.return_value = {"id": 1}
    mock_db_client.add_workflow_step.return_value = 1 # 隨便回傳一個 step_id

    # 執行
    response = api_client.post("/api/workflows/create_from_items", json=request_payload)

    # 斷言
    assert response.status_code == 200
    data = response.json()
    assert data["workflow_id"] == 1
    assert "成功建立工作流 #1 並新增 2 個步驟" in data["message"]

    # 驗證 DB 函式被正確呼叫
    mock_db_client.create_workflow.assert_called_once_with("新任務")
    assert mock_db_client.add_workflow_step.call_count == 2
    mock_db_client.add_workflow_step.assert_any_call(1, {
        "command": "DOWNLOAD_AND_EXTRACT",
        "parameters": {"url": "http://example.com/1", "source_url_id": 1}
    })