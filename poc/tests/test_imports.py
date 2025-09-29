# poc/tests/test_imports.py

import pytest

def test_main_module_can_be_imported():
    """
    驗證重構後的主要啟動模組 (main.py) 可以被 pytest 從專案根目錄成功導入。
    如果此測試通過，代表 `main.py` 及其直接或間接導入的模組
    (如 data_manager, stress_index_calculator 等) 的相對導入路徑都已正確設定，
    從而解決了原始程式碼的 ModuleNotFoundError 問題。
    """
    try:
        # Pytest 從專案根目錄運行，所以這個導入路徑是正確的。
        # 如果這裡成功，代表所有子模組的相對路徑也都設定正確了。
        import poc.bond_data_service_v2.main
    except ImportError as e:
        pytest.fail(f"導入 'poc.bond_data_service_v2.main' 時發生錯誤，請檢查相對導入路徑是否都已修正: {e}")