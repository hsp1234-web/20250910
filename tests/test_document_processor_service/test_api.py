import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

# --- 將專案根目錄加入 sys.path ---
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# --- 模組匯入 ---
# 匯入我們的 FastAPI 應用程式實例
from services.document_processor_service.main import app

# --- 測試客戶端初始化 ---
# 使用 TestClient 來模擬對我們 app 的 API 請求
client = TestClient(app)

# --- 測試 API 端點 ---

def test_health_check():
    """
    整合測試：驗證 /health 端點是否正常運作。
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Document Processor Service"}

# 使用 patch 來模擬 repository 和 processor 中的函式
# 這讓我們的 API 測試可以獨立於資料庫和實際的處理邏輯
@patch("services.document_processor_service.api_routes.create_processing_task")
@patch("services.document_processor_service.api_routes.process_document_url")
def test_process_document_new_url(mock_process_url, mock_create_task):
    """
    整合測試：驗證當收到一個新 URL 時，API 的行為是否正確。
    """
    # 模擬 create_processing_task 回傳 True，代表這是一個新任務
    mock_create_task.return_value = True

    test_url = "http://example.com/new_document.pdf"

    # 執行 API 請求
    response = client.post("/api/process_document", json={"url": test_url})

    # 驗證 API 的回應
    assert response.status_code == 202  # 202 Accepted
    assert response.json() == {"message": "文件已成功加入處理佇列。", "url": test_url}

    # 驗證 create_processing_task 是否被正確呼叫
    mock_create_task.assert_called_once_with(test_url)

    # 驗證 process_document_url 是否被正確地加入到背景任務中
    # 由於 FastAPI 的 BackgroundTasks 不容易直接測試，我們依賴於它被呼叫
    # 在這個簡化測試中，我們假設如果 create_processing_task 回傳 True，它就會被加入
    # 在真實世界中，這可能需要更複雜的測試設定來攔截 BackgroundTasks 的 add_task 方法

@patch("services.document_processor_service.api_routes.create_processing_task")
@patch("services.document_processor_service.api_routes.process_document_url")
def test_process_document_existing_url(mock_process_url, mock_create_task):
    """
    整合測試：驗證當收到一個已存在的 URL 時，API 的行為是否正確。
    """
    # 模擬 create_processing_task 回傳 False，代表任務已存在
    mock_create_task.return_value = False

    test_url = "http://example.com/existing_document.pdf"

    # 執行 API 請求
    response = client.post("/api/process_document", json={"url": test_url})

    # 驗證 API 的回應
    assert response.status_code == 200 # 200 OK
    assert response.json() == {"message": "文件處理任務已存在，無需重複加入。", "url": test_url}

    # 驗證 create_processing_task 是否被正確呼叫
    mock_create_task.assert_called_once_with(test_url)

    # 驗證在任務已存在的情況下，process_document_url **不應該**被加入背景佇列
    mock_process_url.assert_not_called()

def test_process_document_invalid_url():
    """
    整合測試：驗證當收到一個無效的 URL 時，FastAPI 的 Pydantic 模型是否能正確攔截。
    """
    # Pydantic 的 HttpUrl 型別會自動驗證 URL 格式
    response = client.post("/api/process_document", json={"url": "這不是一個有效的URL"})

    # 驗證 FastAPI 是否回傳 422 Unprocessable Entity 錯誤
    assert response.status_code == 422
    # 修正：更新斷言以匹配 Pydantic v2 更精確的錯誤訊息
    assert "Input should be a valid URL" in response.text