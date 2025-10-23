# services/bond_data_service/tests/test_api_routes.py

import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
# 依賴於 bond_data_service 應用程式的實例
from services.bond_data_service.main import app, lifespan

# 備註: `pytest-asyncio` 對於非同步的 lifespan 函數是必要的
# `httpx` 是 TestClient 進行非同步請求時所需要的

# --- 測試設定 ---

@pytest.fixture
def client():
    """
    一個 pytest fixture，用於設定和清理 FastAPI TestClient。
    它會妥善地處理非同步的 lifespan 管理器。
    """
    with TestClient(app) as test_client:
        yield test_client

# --- 測試案例 ---

def test_health_check(client):
    """
    測試 /health 端點是否能成功回應。
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "債券資料服務 (v2) 已就緒。"}

@patch('services.bond_data_service.api_routes.service.calculate_full_metrics')
def test_trigger_update_success(mock_calculate_metrics: MagicMock, client):
    """
    測試 POST /api/trigger_update 端點的核心成功路徑。

    - 使用 @patch 來模擬(mock) `calculate_full_metrics` 方法。
    - 驗證該方法是否被以正確的日期參數呼叫。
    - 驗證 API 是否回傳 HTTP 200 OK。
    - **此測試完全不執行實際的資料抓取或計算。**
    """
    # 安排 (Arrange)
    # 設定模擬函式不回傳任何值，因為我們只關心它是否被呼叫
    mock_calculate_metrics.return_value = None

    test_start_date = "2023-01-01"
    test_end_date = "2023-12-31"

    # 動作 (Act)
    response = client.post(
        "/api/trigger_update",
        json={"start_date": test_start_date, "end_date": test_end_date}
    )

    # 斷言 (Assert)
    # 1. 驗證 API 回應是否成功
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # 2. 驗證被模擬的 `calculate_full_metrics` 函式是否被呼叫了
    mock_calculate_metrics.assert_called_once()

    # 3. 驗證呼叫時傳入的參數是否正確
    #    FastAPI 會自動將 JSON 日期字串轉換為 Pydantic 模型中的 date 物件，
    #    我們的 API 路由接著會將其轉為字串。因此，我們斷言字串是匹配的。
    mock_calculate_metrics.assert_called_with(test_start_date, test_end_date)


def test_trigger_update_invalid_payload(client):
    """
    測試當傳送無效的 payload (例如，非法的日期格式) 給 /api/trigger_update 時，
    FastAPI 的驗證機制是否能正確地回傳 HTTP 422 Unprocessable Entity。
    """
    # 動作 (Act)
    response = client.post(
        "/api/trigger_update",
        json={"start_date": "這不是一個日期", "end_date": "2023-12-31"}
    )

    # 斷言 (Assert)
    assert response.status_code == 422 # Unprocessable Entity


@patch('services.bond_data_service.api_routes.service.calculate_full_metrics', side_effect=Exception("模擬的服務層錯誤"))
def test_trigger_update_service_layer_exception(mock_calculate_metrics: MagicMock, client):
    """
    測試當 `calculate_full_metrics` 方法在執行時拋出例外，
    API 層是否能捕捉到它並回傳一個 HTTP 500 Internal Server Error。
    """
    # 安排 (Arrange)
    # side_effect 讓模擬函式在被呼叫時拋出一個例外

    # 動作 (Act)
    response = client.post(
        "/api/trigger_update",
        json={"start_date": "2023-01-01", "end_date": "2023-12-31"}
    )

    # 斷言 (Assert)
    assert response.status_code == 500
    assert "發生內部錯誤" in response.json()["detail"]
