# poc/tests/test_repository.py

import pytest
import pandas as pd
import sqlite3
from pathlib import Path

# 匯入我們要測試的目標
from poc.bond_data_service_v2 import repository
from poc.bond_data_service_v2.repository import FinancialDataRepository

# --- 測試 Fixtures ---

@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    """
    提供一個指向臨時目錄中的測試資料庫檔案的路徑。
    """
    return tmp_path / "test_bond_data.sqlite3"

@pytest.fixture
def patched_repository_db_file(test_db_path: Path, monkeypatch):
    """
    使用 monkeypatch 來動態地將 repository 模組中的 DB_FILE 常數
    替換為我們的臨時測試資料庫路徑。
    這確保了所有在 repository 模組中的資料庫操作都會發生在隔離的測試資料庫上。
    """
    monkeypatch.setattr(repository, "DB_FILE", test_db_path)

# --- 測試案例 ---

def test_initialize_database(patched_repository_db_file, test_db_path: Path):
    """
    測試：`initialize_database` 函式是否能成功建立資料庫檔案和 `time_series_data` 資料表。
    這是一個整合測試，它會真實地在檔案系統上進行操作。
    """
    # GIVEN: 資料庫檔案不存在
    assert not test_db_path.exists()

    # WHEN: 呼叫初始化函式
    repository.initialize_database()

    # THEN: 驗證檔案和資料表是否已建立
    assert test_db_path.exists()

    # 連接到資料庫並檢查資料表結構
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='time_series_data';")
    table = cursor.fetchone()
    conn.close()

    assert table is not None, "time_series_data 資料表未被建立"
    assert table[0] == "time_series_data"

def test_repository_save_and_load_series(patched_repository_db_file, test_db_path: Path):
    """
    測試：倉儲層是否能正確地儲存和讀取一個 Pandas Series。
    這驗證了資料庫 I/O 的核心邏輯。
    """
    # GIVEN: 一個已初始化的資料庫和一個倉儲實例
    repository.initialize_database()
    repo = FinancialDataRepository()

    # 準備測試數據
    dates = pd.to_datetime(pd.date_range(start="2023-01-01", periods=5))
    test_data = pd.Series([10.1, 10.2, 10.3, 10.4, 10.5], index=dates, name="TEST_TICKER")
    ticker = "TEST_TICKER"
    start_date = "2023-01-01"
    end_date = "2023-01-05"

    # WHEN: 我們呼叫內部方法來儲存和讀取數據
    # 注意：在測試中，為了驗證單元功能，直接呼叫私有方法是可以接受的。
    repo._save_series_to_db(test_data, ticker)
    loaded_data = repo._load_series_from_db(ticker, start_date, end_date)

    # THEN: 驗證讀取出的數據與原始數據完全一致
    assert loaded_data is not None
    # 修正：新增 check_freq=False。因為日期在存入資料庫（轉為字串）再讀出後，會遺失頻率 (freq) 資訊。
    pd.testing.assert_series_equal(test_data, loaded_data, check_names=False, check_freq=False)
    assert loaded_data.name == ticker # 驗證 name 是否被正確設定

def test_load_non_existent_data_returns_none(patched_repository_db_file):
    """
    測試：當嘗試讀取不存在的數據時，倉儲層應返回 None。
    """
    # GIVEN: 一個已初始化的資料庫和一個倉儲實例
    repository.initialize_database()
    repo = FinancialDataRepository()

    # WHEN: 嘗試讀取一個不存在的 ticker
    loaded_data = repo._load_series_from_db("NON_EXISTENT", "2023-01-01", "2023-01-05")

    # THEN: 應返回 None
    assert loaded_data is None