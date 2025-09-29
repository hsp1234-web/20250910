# tests/test_imports.py
import pytest

def test_bond_data_service_import():
    """
    測試 services.bond_data_service.main 是否可以成功導入。
    這是為了解決 ModuleNotFoundError 的第一步。
    """
    try:
        # 我們只導入模組，不執行它，以進行一個純粹的導入測試
        from services.bond_data_service import main as bond_data_service_main
    except ImportError as e:
        pytest.fail(f"導入 services.bond_data_service.main 失敗: {e}")
    except RuntimeError as e:
        # 捕捉在導入時可能發生的執行期錯誤，例如找不到檔案
        pytest.fail(f"導入 services.bond_data_service.main 時發生執行期錯誤: {e}")

# 註解：
# 根據對 src/api/routes/bond_service_proxy.py 的分析，
# "bond_service" 並不是一個獨立的服務，而是由 "bond_data_service" 提供的功能。
# 因此，不存在 services.bond_service 模組。
# 原有的 test_bond_service_import 測試案例已被移除，因為它測試的是一個已不存在的組件。