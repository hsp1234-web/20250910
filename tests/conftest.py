import pytest
import json
from pathlib import Path

@pytest.fixture(scope="session", autouse=True)
def create_test_service_registry():
    """
    (Jules @ 2025-10-11) 重構測試設定以提高穩健性。

    這個 fixture 會在整個測試會話 (session) 開始時自動執行。它會創建一個
    虛擬的服務註冊檔案，這是 `service_discovery` 模組成功運作所必需的。
    這避免了在多個測試中使用 `mocker.patch` 來模擬服務發現的複雜性和脆弱性。

    透過提供一個符合預期的真實環境依賴（即一個檔案），我們讓測試更接近
    實際的整合測試，同時解決了由 `pytest` 模組導入順序引起的 mock 失效問題。
    """
    registry_path = Path("/tmp/service_registry.json")
    registry_content = {
        "line_parser_service": {"port": 8002},
        "document_processor_service": {"port": 8003},
        "stock_id_extractor_service": {"port": 8004}
    }

    # 確保目錄存在
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    # 寫入註冊檔案
    with open(registry_path, 'w', encoding='utf-8') as f:
        json.dump(registry_content, f)

    # 讓測試執行
    yield

    # 測試會話結束後，清理檔案
    try:
        registry_path.unlink()
    except FileNotFoundError:
        pass