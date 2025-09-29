# poc/tests/test_service.py

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock

# 匯入我們要測試的目標
from poc.bond_data_service_v2.service import StressIndexService
from poc.bond_data_service_v2.repository import FinancialDataRepository

# --- 測試資料 ---
# 我們建立一個固定的、可預測的測試數據集
def create_mock_series(name, days=300):
    dates = pd.to_datetime(pd.date_range(end="2023-12-31", periods=days, freq='D'))
    # 根據指標名稱給予一個可預測的假數據
    if name == 'dgs10':
        data = np.linspace(3.5, 4.0, days)
    elif name == 'dgs2':
        data = np.linspace(4.5, 4.2, days)
    elif name == 'sofr':
        data = np.linspace(5.0, 5.2, days)
    else:
        data = np.random.rand(days) * 100

    series = pd.Series(data, index=dates, name=name)
    # 模擬 FRED 數據可能有的缺失值
    series.iloc[::10] = np.nan
    return series

@pytest.fixture
def mock_repository() -> MagicMock:
    """
    建立一個模擬的 FinancialDataRepository。
    這個模擬倉儲在被呼叫 get_series 時，會回傳我們預先定義好的假數據。
    """
    mock_repo = MagicMock(spec=FinancialDataRepository)

    # 定義 get_series 的行為
    def get_series_side_effect(indicator_name, start_date, end_date, force_refresh=False):
        # 模擬不同指標的數據
        indicator_list = [
            "sofr", "dgs10", "dgs2", "vix", "us_high_yield_spread",
            "dealer_net_positions", "wresbal", "rrp",
            "dealer_long_term_positions", "dealer_short_term_positions"
        ]
        if indicator_name in indicator_list:
            return create_mock_series(indicator_name)
        return None

    mock_repo.get_series.side_effect = get_series_side_effect
    return mock_repo

# --- 測試案例 ---

def test_stress_index_service_initialization(mock_repository):
    """
    測試：StressIndexService 是否能被成功初始化。
    """
    service = StressIndexService(repository=mock_repository)
    assert service is not None
    assert service.repository == mock_repository

def test_calculate_full_metrics_with_mock_data(mock_repository):
    """
    測試：核心計算邏輯 calculate_full_metrics 是否能處理模擬數據並產出預期的欄位。
    這是一個關鍵的單元測試，它將業務邏輯與真實的資料來源完全隔離。
    """
    # GIVEN: 一個服務實例，其倉儲已被模擬
    service = StressIndexService(repository=mock_repository)
    start_date = "2023-01-01"
    end_date = "2023-12-31"

    # WHEN: 呼叫核心計算方法
    result_df = service.calculate_full_metrics(start_date, end_date)

    # THEN: 驗證輸出
    assert result_df is not None
    assert isinstance(result_df, pd.DataFrame)
    assert not result_df.empty

    # 驗證衍生的關鍵指標欄位是否存在
    expected_cols = [
        'spread_10y2y',             # 衍生指標
        'sofr_ma60',                # 衍生指標
        'dealer_stress_index',      # 最終產出
        'macd_line',                # 最終產出
        'macd_hist'                 # 最終產出
    ]
    for col in expected_cols:
        assert col in result_df.columns

    # 驗證一個計算值的正確性
    # 根據我們的假數據, 10y-2y 利差應該是負的 (3.5-4.5 = -1.0)
    # 由於數據是線性變化的，我們可以檢查第一個有效值
    first_valid_spread = result_df['spread_10y2y'].dropna().iloc[0]
    assert first_valid_spread < 0, "10-2y 利差計算應為負值"

    # 驗證壓力指數的值在 0-100 之間
    stress_index_series = result_df['dealer_stress_index'].dropna()
    assert stress_index_series.min() >= 0
    assert stress_index_series.max() <= 100