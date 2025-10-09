# tests/api/routes/conftest.py
import pytest

@pytest.fixture(autouse=True)
def mock_get_service_url(mocker):
    """
    自動應用的 fixture，會在這個測試目錄下的所有測試執行前生效。
    它負責 mock 'get_service_url' 函式，避免測試因找不到服務註冊檔案而失敗。
    """
    mocker.patch(
        # 目標是 get_service_url 在被 essay_performance.py 使用時的位置
        "src.api.routes.essay_performance.get_service_url",
        return_value="http://localhost:8001"
    )