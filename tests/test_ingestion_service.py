import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from services.ingestion_service.main import app
from api.dependencies import get_db

# --- Mocking a DB Client ---
@pytest.fixture
def mock_db_client():
    """建立一個 DBClient 的 MagicMock 實例。"""
    db = MagicMock(spec=DBClient)
    # 預先設定一些 mock 方法的回傳值
    db.get_filtered_urls.return_value = [
        {"id": 1, "author": "Jules", "url": "http://example.com/1", "date": "2025-01-01"},
        {"id": 2, "author": "Verne", "url": "http://example.com/2", "date": "2025-01-02"},
    ]
    db.add_new_urls.return_value = None
    return db

@pytest.fixture
def client(mock_db_client):
    """
    提供一個 TestClient 實例，並使用 FastAPI 的依賴注入覆蓋功能
    來確保所有 API 端點都使用我們 mock 的資料庫客戶端。
    """
    app.dependency_overrides[get_db] = lambda: mock_db_client
    yield TestClient(app)
    # 測試結束後清理，恢復原始的依賴項
    app.dependency_overrides.clear()


# --- Test Cases ---

def test_health_check(client):
    """測試 /health 健康檢查端點。"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Ingestion Service"}

def test_extract_urls_endpoint_success(client, mock_db_client):
    """測試 /api/page1/extract_urls 端點的成功情境。"""
    # --- Arrange ---
    test_text = "Jules (2025-01-01 12:00):\n這是一個測試網址 http://example.com/1"

    # --- Act ---
    response = client.post("/api/page1/extract_urls", json={"text": test_text})

    # --- Assert ---
    assert response.status_code == 200
    expected_data = [{
        'author': 'Jules',
        'message_date': '2025-01-01',
        'message_time': '12:00',
        'url': 'http://example.com/1'
    }]
    assert response.json() == expected_data

    # 斷言資料庫客戶端的 add_new_urls 方法被呼叫了一次，且參數正確
    mock_db_client.add_new_urls.assert_called_once_with(expected_data, test_text)

def test_extract_urls_endpoint_empty_text(client, mock_db_client):
    """測試 /api/page1/extract_urls 端點在輸入為空時的錯誤處理。"""
    response = client.post("/api/page1/extract_urls", json={"text": "  "})
    assert response.status_code == 400
    assert response.json() == {"detail": "提供的文字不可為空。"}
    # 斷言資料庫客戶端的方法未被呼叫
    mock_db_client.add_new_urls.assert_not_called()

def test_get_overview_data_endpoint(client, mock_db_client):
    """測試 /api/page1/overview_data 端點。"""
    response = client.get("/api/page1/overview_data")
    assert response.status_code == 200
    # 斷言回傳的資料與我們在 mock_db_client 中設定的相符
    assert response.json() == [
        {"id": 1, "author": "Jules", "url": "http://example.com/1", "date": "2025-01-01"},
        {"id": 2, "author": "Verne", "url": "http://example.com/2", "date": "2025-01-02"},
    ]
    # 斷言 get_filtered_urls 方法被呼叫
    mock_db_client.get_filtered_urls.assert_called_once()

def test_export_data_as_csv(client, mock_db_client):
    """測試 /api/page1/export 端點匯出 CSV 的功能。"""
    response = client.get("/api/page1/export?format=csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment; filename=export.csv" in response.headers["content-disposition"]

    # 檢查 CSV 內容是否符合預期
    csv_content = response.text
    expected_csv = "message_date,author,url\n2025-01-01,Jules,http://example.com/1\n2025-01-02,Verne,http://example.com/2\n"
    assert csv_content.replace('\r\n', '\n') == expected_csv
