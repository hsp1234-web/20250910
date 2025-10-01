# tests/test_stress_index_calculator.py

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

# 修正：匯入重構後的 v2 服務
from services.bond_data_service.bond_data_service_v2.service import StressIndexService

@pytest.fixture(autouse=True)
def clear_cache_before_test():
    """
    一個在每個測試函式執行前自動執行的 fixture，
    確保我們的快取測試不會受到其他測試案例的影響。
    """
    # 修正：透過類別存取靜態的快取實例
    StressIndexService.metrics_cache.clear()
    yield # 這是測試執行的地方
    StressIndexService.metrics_cache.clear()

def test_calculate_full_metrics_caching_logic():
    """
    測試 `calculate_full_metrics` 函式的快取機制是否正常運作。
    """
    # 1. 準備 mock 物件
    # 修正：現在我們需要 mock FinancialDataRepository 而不是 DataManager
    mock_repository = MagicMock()

    # 創建一個假的 DataFrame，模擬從 repository.get_series 返回的數據
    # 這樣可以讓函式順利執行，而不需要依賴真實的數據抓取
    fake_series = pd.Series([1.0, 1.1, 1.2], name='fake_data')
    mock_repository.get_series.return_value = fake_series

    # 2. 使用 patch 來監控函式內部的一個關鍵計算步驟
    # 我們選擇 patch `pd.concat`，因為它在每次完整計算中是關鍵的資料彙總步驟。
    # 如果快取命中，這個函式就不會被呼叫。

    # 準備一個更逼真的假 DataFrame，包含函式執行所需的所有欄位
    fake_data_for_concat = {
        'sofr': [1.0, 1.1, 1.2] * 100,
        'dgs10': [2.5, 2.6, 2.7] * 100,
        'dgs2': [2.0, 2.1, 2.2] * 100,
        'vix': [15, 16, 17] * 100,
        'us_high_yield_spread': [3.5, 3.6, 3.7] * 100,
        'dealer_net_positions': [100, 110, 120] * 100,
        'wresbal': [1000, 1010, 1020] * 100,
        'rrp': [50, 55, 60] * 100,
        'dealer_long_term_positions': [70, 80, 90] * 100,
        'dealer_short_term_positions': [30, 30, 30] * 100,
    }
    # 建立一個足夠長的日期索引以避免其他計算（如滾動平均）出錯
    date_range = pd.to_datetime(pd.date_range(start='2022-01-01', periods=300))
    fake_df = pd.DataFrame(fake_data_for_concat, index=date_range)

    # 修正：patch 新的模組路徑
    with patch('services.bond_data_service.bond_data_service_v2.service.pd.concat', return_value=fake_df) as mock_concat:
        # 修正：建立 StressIndexService 的實例
        service_instance = StressIndexService(repository=mock_repository)

        # 3. 第一次呼叫 (應該觸發計算)
        print("第一次呼叫，預期會觸發計算...")
        service_instance.calculate_full_metrics('2023-01-01', '2023-12-31')
        assert mock_concat.call_count == 1, "第一次呼叫時，內部計算 (concat) 應該被執行一次"
        print(f"呼叫後，concat 執行次數: {mock_concat.call_count}")

        # 4. 第二次呼叫 (使用完全相同的參數，應該命中快取)
        print("\n第二次呼叫 (相同參數)，預期會命中快取...")
        service_instance.calculate_full_metrics('2023-01-01', '2023-12-31')
        assert mock_concat.call_count == 1, "第二次呼叫相同參數時，內部計算不應再次執行，執行次數應維持在 1"
        print(f"呼叫後，concat 執行次數: {mock_concat.call_count}")

        # 5. 第三次呼叫 (使用不同的參數，應該再次觸發計算)
        print("\n第三次呼叫 (不同參數)，預期會再次觸發計算...")
        service_instance.calculate_full_metrics('2024-01-01', '2024-12-31')
        assert mock_concat.call_count == 2, "第三次呼叫不同參數時，應觸發新的計算，執行次數應變為 2"
        print(f"呼叫後，concat 執行次數: {mock_concat.call_count}")

        # 6. 驗證快取鍵是否忽略了 repository
        # 修正：建立一個新的 mock repository 實例
        another_mock_repository = MagicMock()
        another_mock_repository.get_series.return_value = fake_series
        another_service_instance = StressIndexService(repository=another_mock_repository)

        print("\n第四次呼叫 (相同日期，但不同 repository 實例)，預期仍會命中快取...")
        # 修正：使用新的服務實例呼叫
        another_service_instance.calculate_full_metrics('2023-01-01', '2023-12-31')
        assert mock_concat.call_count == 2, "即使 repository 物件不同，只要日期相同，也應命中快取"
        print(f"呼叫後，concat 執行次數: {mock_concat.call_count}")