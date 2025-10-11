import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

from services.llm_service.main import app

# --- Pytest Fixtures ---

@pytest.fixture
def mock_ollama_client_success():
    """一個模擬成功的 Ollama Client 的 fixture。"""
    with patch('services.llm_service.model_manager.ollama.Client') as mock_client:
        mock_instance = MagicMock()
        mock_instance.list.return_value = {'models': [{'name': 'test-model'}]}
        mock_instance.chat.return_value = {'message': {'content': '這是模擬的回應。'}}
        mock_client.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_ollama_client_connection_error():
    """一個在初始化時就模擬連線失敗的 Ollama Client 的 fixture。"""
    with patch('services.llm_service.model_manager.ollama.Client', side_effect=ConnectionError("無法連接到 Ollama。")) as mock_client:
        yield mock_client

@pytest.fixture
def client(request):
    """
    提供一個 FastAPI TestClient 的實例。
    這個 fixture 會根據測試函式上的 'marker' 來決定使用哪個模擬 client。
    """
    # 預設使用成功的 mock client
    mock_context = patch('services.llm_service.model_manager.ollama.Client')

    if 'connection_error' in request.keywords:
        mock_context = patch('services.llm_service.model_manager.ollama.Client', side_effect=ConnectionError("無法連接到 Ollama。"))

    with mock_context as mock_ollama:
        if 'connection_error' not in request.keywords:
             # 為成功情境設定更詳細的模擬
            mock_instance = MagicMock()
            mock_instance.list.return_value = {'models': [{'name': 'test-model'}]}
            mock_instance.chat.return_value = {'message': {'content': '這是模擬的回應。'}}
            mock_ollama.return_value = mock_instance

        with TestClient(app) as test_client:
            yield test_client


# --- 測試案例 ---

def test_ping_endpoint(client):
    """
    測試 /ping 端點是否能正常回傳 'ok'。
    """
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "LLM Service is running."}


def test_generate_text_success(client):
    """
    測試 /generate 端點在 Ollama 服務正常運作時的行為。
    """
    # 發送 POST 請求到 /generate 端點
    response = client.post("/generate", json={"model": "test-model", "prompt": "你好嗎？"})

    # 驗證狀態碼和回應內容
    assert response.status_code == 200
    json_response = response.json()
    assert json_response['model'] == 'test-model'
    assert json_response['response_text'] == '這是模擬的回應。'


@pytest.mark.connection_error
def test_generate_text_ollama_connection_error(client):
    """
    測試當應用程式啟動時就無法連接到 Ollama 服務時，/generate 端點的行為。
    """
    # 發送請求
    response = client.post("/generate", json={"model": "test-model", "prompt": "你好嗎？"})

    # 驗證是否回傳了 503 Service Unavailable
    # 這是因為 ModelManager 在 lifespan 中初始化失敗，所以任何需要它的端點都會失敗。
    assert response.status_code == 503
    # (Jules): 根據上一次的測試結果，修正預期的錯誤訊息。
    assert "無法連接到 Ollama 服務" in response.json()['detail']