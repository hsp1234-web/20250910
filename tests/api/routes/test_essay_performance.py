# tests/api/routes/test_essay_performance.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
import httpx

# --- 測試設定 ---
import os
os.environ['API_MODE'] = 'mock'

# (Jules @ 2025-10-11) 移除全域的 app 匯入。
# 在全域範圍匯入 app 會導致在 conftest.py 的 mock 生效前就載入路由，
# 使得 mock 失效。正確的做法是透過 fixture 延遲 app 的匯入與 TestClient 的實例化。

# --- 測試客戶端 Fixture ---
@pytest.fixture
def client():
    """
    建立一個 TestClient 實例。
    透過在 fixture 內部延遲 TestClient 的實例化，
    我們確保 conftest.py 中的 autouse mocks 已經生效。
    """
    # 延遲匯入和實例化，確保 mock 已被應用
    from src.api.api_server import app
    with TestClient(app) as test_client:
        yield test_client


# (Jules @ 2025-10-11) 移除對 mock_httpx_post 的依賴，因為 conftest.py 中的
# 新 fixture 提供了更真實的服務發現機制。現在我們需要 mock httpx.post 來模擬
# 對下游服務的呼叫。

@pytest.fixture
def mock_httpx_client(mocker):
    """Mock aiohttp.ClientSession aenter and post methods."""
    mock_post = AsyncMock()
    mock_client = MagicMock()
    mock_client.post = mock_post

    # We need to mock the context manager
    mock_async_context_manager = MagicMock()
    mock_async_context_manager.__aenter__.return_value = mock_client

    mocker.patch('httpx.AsyncClient', return_value=mock_async_context_manager)
    return mock_post

def test_proxy_ingest_text_success(client: TestClient, mock_httpx_client: AsyncMock):
    """
    測試代理端點在成功情況下的行為。
    """
    # 1. 準備模擬的回應
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": "來自模擬微服務的回應", "inserted_count": 1}
    mock_response.raise_for_status.return_value = None
    mock_httpx_client.return_value = mock_response

    # 2. 執行測試
    test_payload = {"text": "這是一段測試文字"}
    response = client.post("/api/essay_performance/ingest_text", json=test_payload)

    # 3. 進行斷言
    assert response.status_code == 200
    assert response.json()["message"] == "來自模擬微服務的回應"
    mock_httpx_client.assert_called_once_with(
        "http://127.0.0.1:8001/ingest",
        json=test_payload,
        timeout=30.0
    )


def test_proxy_ingest_text_service_unavailable(client: TestClient, mock_httpx_client: AsyncMock):
    """
    測試當微服務無法連線時，代理端點是否回傳 503。
    """
    # 1. 設定 mock 以引發連線錯誤
    mock_httpx_client.side_effect = httpx.RequestError("連線被拒", request=MagicMock())

    # 2. 執行測試
    test_payload = {"text": "測試文字"}
    response = client.post("/api/essay_performance/ingest_text", json=test_payload)

    # 3. 進行斷言
    assert response.status_code == 503
    assert "後端擷取服務目前無法使用" in response.json()["detail"]


def test_proxy_ingest_text_service_returns_error(client: TestClient, mock_httpx_client: AsyncMock):
    """
    測試當微服務本身回傳一個錯誤狀態碼時，代理端點是否能正確轉發。
    """
    # 1. 準備模擬的錯誤回應
    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 400
    mock_error_response.text = '{"detail":"Bad Request"}'
    mock_error_response.json.return_value = {"detail": "微服務說你的請求格式錯誤"}

    # 建立一個會引發 HTTPStatusError 的 mock
    mock_error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Bad Request", request=MagicMock(), response=mock_error_response
    )

    mock_httpx_client.return_value = mock_error_response

    # 2. 執行測試
    test_payload = {"text": "一個會導致錯誤的請求"}
    response = client.post("/api/essay_performance/ingest_text", json=test_payload)

    # 3. 進行斷言
    assert response.status_code == 400
    assert response.json()["detail"] == {"detail": "微服務說你的請求格式錯誤"}


def test_start_download_no_ids(client: TestClient):
    """
    測試當請求的 ID 列表為空時，/start_download 是否回傳 400 錯誤。
    """
    response = client.post("/api/essay_performance/start_download", json={"ids": []})
    assert response.status_code == 400
    assert "ID列表不可為空" in response.json()["detail"]


def test_get_status_not_found(client: TestClient):
    """
    測試查詢一個不存在的任務 ID 時，/status/{task_id} 是否回傳 404 錯誤。
    """
    non_existent_task_id = "this-task-does-not-exist"
    response = client.get(f"/api/essay_performance/status/{non_existent_task_id}")
    assert response.status_code == 404
    assert f"找不到任務ID: {non_existent_task_id}" in response.json()["detail"]