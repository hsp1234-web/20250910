import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

# 這次我們測試的是主應用程式中的代理路由，所以從 api_server 匯入 app
from src.api.api_server import app

@pytest.fixture
def client():
    """提供一個 TestClient 實例。"""
    return TestClient(app)

@patch('src.api.routes.page6_keys.get_service_url')
@patch('src.api.routes.page6_keys.requests.request')
def test_get_keys_proxy_success(mock_requests_request, mock_get_service_url, client):
    """
    測試 page6_keys 代理在後端服務成功回應時的行為。
    """
    # --- Arrange ---
    # 模擬 get_service_url 總是回傳一個固定的假 URL
    mock_get_service_url.return_value = "http://fake-key-service:8002"

    # 建立一個 mock response 物件
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"key_hash": "abc", "status": "valid"}]

    # 讓 requests.request 回傳我們的 mock response
    mock_requests_request.return_value = mock_response

    # --- Act ---
    # 透過 TestClient 呼叫主應用程式的代理端點
    response = client.get("/api/keys")

    # --- Assert ---
    # 斷言代理是否正確回傳了後端服務的狀態碼和內容
    assert response.status_code == 200
    assert response.json() == [{"key_hash": "abc", "status": "valid"}]

    # 斷言 get_service_url 和 requests.request 是否被呼叫
    mock_get_service_url.assert_called_once_with("key_service")
    mock_requests_request.assert_called_once()
    # 檢查呼叫 requests.request 時的參數是否正確
    call_args, call_kwargs = mock_requests_request.call_args
    assert call_kwargs['method'] == 'GET'
    assert call_kwargs['url'] == "http://fake-key-service:8002/api/keys"


@patch('src.api.routes.page6_keys.get_service_url')
@patch('src.api.routes.page6_keys.requests.request')
def test_get_keys_proxy_backend_error(mock_requests_request, mock_get_service_url, client):
    """
    測試 page6_keys 代理在後端服務回傳錯誤時的行為。
    """
    # --- Arrange ---
    mock_get_service_url.return_value = "http://fake-key-service:8002"

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.json.return_value = {"detail": "後端服務內部錯誤"}

    mock_requests_request.return_value = mock_response

    # --- Act ---
    response = client.get("/api/keys")

    # --- Assert ---
    # 斷言代理是否正確地將後端服務的錯誤狀態碼和內容轉發回來
    assert response.status_code == 500
    assert response.json() == {"detail": "後端服務內部錯誤"}

@patch('src.api.routes.page6_keys.get_service_url')
@patch('src.api.routes.page6_keys.requests.request')
def test_add_key_proxy_with_payload(mock_requests_request, mock_get_service_url, client):
    """
    測試代理 POST 請求時是否能正確轉發 JSON payload。
    """
    # --- Arrange ---
    mock_get_service_url.return_value = "http://fake-key-service:8002"

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"message": "Key added successfully"}

    mock_requests_request.return_value = mock_response

    key_payload = {"api_key": "sk-12345"}

    # --- Act ---
    response = client.post("/api/keys", json=key_payload)

    # --- Assert ---
    assert response.status_code == 201
    assert response.json() == {"message": "Key added successfully"}

    # 斷言 requests.request 被呼叫時，json 參數包含了我們的 payload
    call_args, call_kwargs = mock_requests_request.call_args
    assert call_kwargs['method'] == 'POST'
    assert call_kwargs['json'] == key_payload
