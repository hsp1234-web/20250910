# services/bond_data_service/tests/test_api_routes.py

import pytest
import pandas as pd
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from services.bond_data_service.main import app

# 標記所有測試為 asyncio 模式
pytestmark = pytest.mark.asyncio

@pytest.fixture
def client():
    """提供一個 FastAPI TestClient。"""
    with TestClient(app) as test_client:
        yield test_client

async def test_health_check(client):
    """測試 /health 端點，現在這是一個異步函式。"""
    response = client.get("/health")
    assert response.status_code == 200
    # 更新斷言以匹配新的回應訊息
    assert response.json() == {"status": "ok", "message": "債券資料分析服務已就緒。"}

@patch('services.bond_data_service.api_routes.service.calculate_full_metrics', new_callable=AsyncMock)
async def test_get_chart_data_ready(mock_calculate_metrics, client):
    """
    測試當資料已就緒 (快取命中) 時，/data/{chart_id} 端點的行為。
    """
    # 安排 (Arrange)
    # 模擬 service 層返回一個假的 DataFrame 和 True (表示資料就緒)
    mock_df = pd.DataFrame({'dealer_stress_index': [50, 51]}, index=pd.to_datetime(['2023-01-01', '2023-01-02']))
    mock_calculate_metrics.return_value = (mock_df, True)

    test_chart_id = "stress_index"
    params = {"start_date": "2023-01-01", "end_date": "2023-01-02"}

    # 動作 (Act)
    response = client.get(f"/data/{test_chart_id}", params=params)

    # 斷言 (Assert)
    assert response.status_code == 200
    # 驗證模擬函式被正確呼叫
    mock_calculate_metrics.assert_awaited_once_with(params["start_date"], params["end_date"])
    # 驗證回應的 JSON 內容是否符合預期
    assert len(response.json()) == 2
    assert response.json()[0]['dealer_stress_index'] == 50

@patch('services.bond_data_service.api_routes.service.calculate_full_metrics', new_callable=AsyncMock)
async def test_get_chart_data_processing(mock_calculate_metrics, client):
    """
    測試當資料正在準備中 (快取未命中) 時，/data/{chart_id} 端點的行為。
    """
    # 安排 (Arrange)
    # 模擬 service 層返回 (None, False) 表示資料正在背景抓取
    mock_calculate_metrics.return_value = (None, False)

    test_chart_id = "stress_index"
    params = {"start_date": "2023-01-01", "end_date": "2023-01-02"}

    # 動作 (Act)
    response = client.get(f"/data/{test_chart_id}", params=params)

    # 斷言 (Assert)
    assert response.status_code == 202 # Accepted
    assert "正在準備中" in response.json()["message"]
    mock_calculate_metrics.assert_awaited_once_with(params["start_date"], params["end_date"])

@patch('services.bond_data_service.api_routes.service.calculate_full_metrics', new_callable=AsyncMock)
async def test_get_chart_data_service_exception(mock_calculate_metrics, client):
    """
    測試當 service 層在計算時拋出例外，API 是否能正確回傳 500 錯誤。
    """
    # 安排 (Arrange)
    # 模擬 service 層拋出一個例外
    mock_calculate_metrics.side_effect = Exception("模擬的服務層計算錯誤")

    test_chart_id = "stress_index"
    params = {"start_date": "2023-01-01", "end_date": "2023-01-02"}

    # 動作 (Act)
    response = client.get(f"/data/{test_chart_id}", params=params)

    # 斷言 (Assert)
    assert response.status_code == 500
    assert "發生內部錯誤" in response.json()["detail"]
    mock_calculate_metrics.assert_awaited_once_with(params["start_date"], params["end_date"])
