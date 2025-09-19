import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

# --- 路徑修正與模組匯入 ---
# 確保能夠從 tests/ 找到 services/backup_service/main.py
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from services.backup_service.main import app

@pytest.fixture
def client():
    """提供一個 TestClient 實例。"""
    return TestClient(app)

@patch('services.backup_service.main.run_backup_task')
def test_start_backup_api_endpoint(mock_run_backup_task, client):
    """
    測試 /start_backup 端點是否能成功接收請求並觸發背景任務。
    我們直接模擬整個背景任務函式，因為我們只關心 API 層是否正確。
    """
    # --- Act ---
    response = client.post("/start_backup")

    # --- Assert ---
    # 斷言 API 回應是否正確
    assert response.status_code == 202
    assert response.json() == {"message": "備份服務已成功接收請求並建立背景任務。"}

    # 斷言背景任務函式被呼叫了一次
    mock_run_backup_task.assert_called_once()


@patch('services.backup_service.main.upload_to_google_drive')
@patch('services.backup_service.main.create_backup_archive')
def test_run_backup_task_logic_success(mock_create_archive, mock_upload_drive):
    """
    直接測試 run_backup_task 函式的內部邏輯（成功情境）。
    """
    # --- Arrange ---
    # 設定 mock 回傳值
    mock_archive_path = "/tmp/backup_test.zip"
    mock_drive_url = "https://fake.drive.url/backup_test.zip"
    mock_create_archive.return_value = mock_archive_path
    mock_upload_drive.return_value = mock_drive_url

    # --- Act ---
    from services.backup_service.main import run_backup_task
    run_backup_task()

    # --- Assert ---
    # 斷言底層工具函式是否被正確呼叫
    mock_create_archive.assert_called_once()
    mock_upload_drive.assert_called_once_with(mock_archive_path)

@patch('services.backup_service.main.upload_to_google_drive')
@patch('services.backup_service.main.create_backup_archive')
def test_run_backup_task_logic_failure(mock_create_archive, mock_upload_drive):
    """
    直接測試 run_backup_task 函式的內部邏輯（失敗情境）。
    """
    # --- Arrange ---
    # 模擬建立壓縮檔失敗
    mock_create_archive.return_value = None

    # --- Act ---
    from services.backup_service.main import run_backup_task
    # 我們預期日誌會記錄一個 RuntimeError，但函式本身會捕捉異常，所以不會拋出
    run_backup_task()

    # --- Assert ---
    # 斷言只有建立壓縮檔的函式被呼叫
    mock_create_archive.assert_called_once()
    # 斷言上傳函式未被呼叫，因為第一步就失敗了
    mock_upload_drive.assert_not_called()

def test_health_check(client):
    """
    測試 /health 健康檢查端點。
    """
    # --- Act ---
    response = client.get("/health")

    # --- Assert ---
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Backup Service"}
