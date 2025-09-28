# tests/test_stress_index_calculator.py

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

# 在匯入被測試的模組之前，我們可能需要確保其相依的模組可以被找到
# 這裡我們直接從 services 目錄下匯入
from services.bond_data_service import stress_index_calculator

# 為了能在測試中控制快取，我們直接匯入快取實例
from services.bond_data_service.stress_index_calculator import metrics_cache

@pytest.fixture(autouse=True)
def clear_cache_before_test():
    """
    一個在每個測試函式執行前自動執行的 fixture，
    確保我們的快取測試不會受到其他測試案例的影響。
    """
    metrics_cache.clear()
    yield # 這是測試執行的地方
    metrics_cache.clear()

def test_calculate_full_metrics_caching_logic():
    """
    測試 `calculate_full_metrics` 函式的快取機制是否正常運作。
    """
    # 1. 準備 mock 物件
    # 我們不需要一個真正的 DataManager，只需要一個可以被呼叫的 mock 物件
    mock_data_manager = MagicMock()

    # 創建一個假的 DataFrame，模擬從 data_manager.get_series 返回的數據
    # 這樣可以讓函式順利執行，而不需要依賴真實的數據抓取
    fake_series = pd.Series([1.0, 1.1, 1.2], name='fake_data')
    mock_data_manager.get_series.return_value = fake_series

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


    with patch('services.bond_data_service.stress_index_calculator.pd.concat', return_value=fake_df) as mock_concat:

        # 3. 第一次呼叫 (應該觸發計算)
        print("第一次呼叫，預期會觸發計算...")
        stress_index_calculator.calculate_full_metrics(mock_data_manager, '2023-01-01', '2023-12-31')
        assert mock_concat.call_count == 1, "第一次呼叫時，內部計算 (concat) 應該被執行一次"
        print(f"呼叫後，concat 執行次數: {mock_concat.call_count}")

        # 4. 第二次呼叫 (使用完全相同的參數，應該命中快取)
        print("\n第二次呼叫 (相同參數)，預期會命中快取...")
        stress_index_calculator.calculate_full_metrics(mock_data_manager, '2023-01-01', '2023-12-31')
        assert mock_concat.call_count == 1, "第二次呼叫相同參數時，內部計算不應再次執行，執行次數應維持在 1"
        print(f"呼叫後，concat 執行次數: {mock_concat.call_count}")

        # 5. 第三次呼叫 (使用不同的參數，應該再次觸發計算)
        print("\n第三次呼叫 (不同參數)，預期會再次觸發計算...")
        stress_index_calculator.calculate_full_metrics(mock_data_manager, '2024-01-01', '2024-12-31')
        assert mock_concat.call_count == 2, "第三次呼叫不同參數時，應觸發新的計算，執行次數應變為 2"
        print(f"呼叫後，concat 執行次數: {mock_concat.call_count}")

        # 6. 驗證快取鍵是否忽略了 data_manager
        # 建立一個新的 mock data_manager 實例
        another_mock_data_manager = MagicMock()
        another_mock_data_manager.get_series.return_value = fake_series

        print("\n第四次呼叫 (相同日期，但不同 data_manager 實例)，預期仍會命中快取...")
        stress_index_calculator.calculate_full_metrics(another_mock_data_manager, '2023-01-01', '2023-12-31')
        assert mock_concat.call_count == 2, "即使 data_manager 物件不同，只要日期相同，也應命中快取"
        print(f"呼叫後，concat 執行次數: {mock_concat.call_count}")