# tests/api/routes/test_essay_performance.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
import httpx

# --- 測試設定 ---
import os
os.environ['API_MODE'] = 'mock'

try:
    from src.api.api_server import app
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
    from src.api.api_server import app

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


@pytest.fixture
def mock_httpx_post(mocker):
    """
    一個更穩健的 fixture，直接 mock 掉 httpx.AsyncClient 的 post 方法。
    這能確保任何地方的 httpx 呼叫都會被攔截。
    """
    # 建立一個非同步 mock 來代表 post 方法
    mock_post_method = AsyncMock()

    # 我們需要 mock AsyncClient 的 __aenter__ (即 'async with' 的進入點)
    # 讓它回傳一個帶有我們 mock_post_method 的物件
    mock_client_instance = AsyncMock()
    mock_client_instance.post = mock_post_method

    # 使用 mocker.patch 來替換掉整個 httpx.AsyncClient 類別
    # 當 httpx.AsyncClient() 被呼叫時，它會回傳一個實例，
    # 該實例的 __aenter__ 方法被設定為回傳我們完全控制的 mock_client_instance
    mocker.patch(
        "httpx.AsyncClient.__aenter__",
        return_value=mock_client_instance
    )

    # fixture 回傳這個 post 方法的 mock，以便在測試中進行設定和斷言
    return mock_post_method


def test_proxy_ingest_text_success(client: TestClient, mock_httpx_post: AsyncMock):
    """
    測試代理端點在成功情況下的行為。
    """
    # 1. 準備模擬的回應
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": "來自模擬微服務的回應", "inserted_count": 1}
    mock_response.raise_for_status.return_value = None
    mock_httpx_post.return_value = mock_response

    # 2. 執行測試
    test_payload = {"text": "這是一段測試文字"}
    response = client.post("/api/essay_performance/ingest_text", json=test_payload)

    # 3. 進行斷言
    assert response.status_code == 200
    assert response.json()["message"] == "來自模擬微服務的回應"
    mock_httpx_post.assert_called_once_with(
        "http://localhost:8001/ingest",
        json=test_payload,
        timeout=30.0
    )


def test_proxy_ingest_text_service_unavailable(client: TestClient, mock_httpx_post: AsyncMock):
    """
    測試當微服務無法連線時，代理端點是否回傳 503。
    """
    # 1. 設定 mock 以引發連線錯誤
    mock_httpx_post.side_effect = httpx.RequestError("連線被拒", request=MagicMock())

    # 2. 執行測試
    test_payload = {"text": "測試文字"}
    response = client.post("/api/essay_performance/ingest_text", json=test_payload)

    # 3. 進行斷言
    assert response.status_code == 503
    assert "後端擷取服務目前無法使用" in response.json()["detail"]


def test_proxy_ingest_text_service_returns_error(client: TestClient, mock_httpx_post: AsyncMock):
    """
    測試當微服務本身回傳一個錯誤狀態碼時，代理端點是否能正確轉發。
    """
    # 1. 準備模擬的錯誤回應
    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 400
    mock_error_response.json.return_value = {"detail": "微服務說你的請求格式錯誤"}
    mock_error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Bad Request", request=MagicMock(), response=mock_error_response
    )
    mock_httpx_post.return_value = mock_error_response

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