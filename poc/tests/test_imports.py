# poc/tests/test_imports.py
# 繁體中文註解：導入測試

def test_import_main_module():
    """
    測試是否可以成功導入主模組。
    這個測試的目的是為了驗證在修正導入路徑之前，
    目前的程式碼結構在標準 pytest 環境下會導入失敗。
    """
    import poc.bond_data_service_v2.main