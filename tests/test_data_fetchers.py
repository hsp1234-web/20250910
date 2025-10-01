import unittest
import pandas as pd
from unittest.mock import patch, MagicMock
from datetime import datetime
import os
import sys

# 確保測試執行時可以找到 'services' 模組
# 執行測試時，請在專案根目錄使用 `PYTHONPATH=. python -m pytest`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.bond_data_service.bond_data_service_v2.data_fetchers import (
    nyfed_positions_fetcher,
    fred_sofr_fetcher,
    fred_vix_fetcher,
)
from services.bond_data_service.bond_data_service_v2.repository import FinancialDataRepository


class TestDataFetchers(unittest.TestCase):
    """
    針對 bond_data_service_v2 中的資料抓取器和倉儲進行單元測試。
    """

    def test_fetch_nyfed_total_positions_data_returns_series(self):
        """
        測試：驗證 nyfed_positions_fetcher 能否成功抓取並回傳一個 pandas Series。
        這是一個小型整合測試，會實際發出網路請求，因為其資料來源是公開的 Excel 檔案。
        """
        print("\n[測試] 正在執行紐約聯儲部位數據抓取器的整合測試...")
        start_date = "2023-01-01"
        end_date = "2023-03-31"

        # 呼叫實際的抓取函式
        result_series = nyfed_positions_fetcher.fetch_nyfed_total_positions_data(
            start_date=start_date, end_date=end_date
        )

        # 斷言結果
        self.assertIsNotNone(result_series, "抓取結果不應為 None")
        self.assertIsInstance(result_series, pd.Series, "抓取結果應為 pandas Series")
        self.assertFalse(result_series.empty, "回傳的 Series 不應為空，如果此斷言失敗，請檢查紐約聯儲的 URL 是否已變更。")
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result_series.index), "Series 的索引應為日期時間格式")
        print("[成功] 紐約聯儲部位數據抓取器測試通過。")

    @patch('services.bond_data_service.bond_data_service_v2.data_fetchers.fred_sofr_fetcher.Fred')
    @patch('services.bond_data_service.bond_data_service_v2.repository.FinancialDataRepository._save_series_to_db')
    def test_fetch_sofr_data_with_mock(self, mock_save_db, mock_fred):
        """
        測試：使用 mock 來驗證 fred_sofr_fetcher 的邏輯，而不發出實際網路請求。
        """
        print("\n[測試] 正在執行 FRED SOFR 數據抓取器的單元測試 (使用 mock)...")
        # 準備 mock
        mock_fred_instance = MagicMock()
        dates = pd.to_datetime(['2023-01-02', '2023-01-03'])
        mock_data = pd.Series([4.3, 4.31], index=dates, name='SOFR')
        mock_fred_instance.get_series.return_value = mock_data
        mock_fred.return_value = mock_fred_instance

        # 呼叫被測試的函式
        # 注意：在 v2 架構中，抓取器本身不儲存數據，而是由 Repository 儲存。
        # 因此這裡我們直接測試抓取器，並驗證其回傳值。
        result_series = fred_sofr_fetcher.fetch_sofr_data(
            api_key="DUMMY_API_KEY",
            start_date="2023-01-01",
            end_date="2023-01-31"
        )

        # 斷言
        mock_fred.assert_called_once_with(api_key="DUMMY_API_KEY")
        mock_fred_instance.get_series.assert_called_once_with(
            'SOFR',
            observation_start="2023-01-01",
            observation_end="2023-01-31"
        )
        self.assertIsInstance(result_series, pd.Series, "回傳值應為 Series")
        self.assertEqual(result_series.name, 'sofr', "Series 名稱應為 'sofr'")
        pd.testing.assert_series_equal(result_series, pd.Series([4.3, 4.31], index=dates, name='sofr'))
        # 在新架構中，抓取器不呼叫 save_series_to_db，所以我們預期它不被呼叫
        mock_save_db.assert_not_called()
        print("[成功] FRED SOFR 數據抓取器單元測試通過。")

    @patch('services.bond_data_service.bond_data_service_v2.repository.get_fred_api_key')
    @patch('services.bond_data_service.bond_data_service_v2.repository.FinancialDataRepository._load_series_from_db')
    @patch('services.bond_data_service.bond_data_service_v2.repository.FinancialDataRepository._save_series_to_db')
    @patch('services.bond_data_service.bond_data_service_v2.data_fetchers.fred_vix_fetcher.fetch_vix_data')
    def test_repository_get_series_cache_miss(self, mock_fetch_vix, mock_save_db, mock_load_from_db, mock_get_key):
        """
        測試：驗證當快取未命中時，Repository.get_series 是否會呼叫網路抓取器並儲存結果。
        """
        print("\n[測試] 正在執行 Repository.get_series 的單元測試 (快取未命中)...")
        # 準備 mock
        mock_get_key.return_value = "DUMMY_API_KEY"
        mock_load_from_db.return_value = None # 模擬快取未命中

        dates = pd.to_datetime(['2023-01-02', '2023-01-03'])
        mock_vix_data = pd.Series([22.0, 21.5], index=dates, name='vix')
        mock_fetch_vix.return_value = mock_vix_data

        repo = FinancialDataRepository()

        # 呼叫被測試的函式
        result = repo.get_series("vix", "2023-01-01", "2023-01-31")

        # 斷言
        mock_load_from_db.assert_called_once_with("VIXCLS", "2023-01-01", "2023-01-31")
        mock_fetch_vix.assert_called_once() # 驗證網路抓取器被呼叫
        mock_save_db.assert_called_once() # 驗證儲存函式被呼叫
        self.assertIsNotNone(result)
        pd.testing.assert_series_equal(result, mock_vix_data)
        print("[成功] Repository.get_series (快取未命中) 測試通過。")


if __name__ == '__main__':
    unittest.main()