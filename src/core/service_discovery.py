import json
from pathlib import Path
import logging
from typing import Optional
import os

# --- 日誌設定 ---
log = logging.getLogger(__name__)

# --- 常數定義 ---
SERVICE_REGISTRY_FILE = Path("/tmp/service_registry.json")

def get_service_url(service_name: str) -> Optional[str]:
    """
    從服務註冊檔案中讀取指定服務的 URL。
    在測試環境中，會優先從 MOCK_SERVICE_REGISTRY 環境變數讀取。
    """
    registry = None
    # 優先從環境變數讀取 (用於測試)
    mock_registry_json = os.environ.get("MOCK_SERVICE_REGISTRY")
    if mock_registry_json:
        try:
            registry = json.loads(mock_registry_json)
            log.debug("使用來自 MOCK_SERVICE_REGISTRY 環境變數的模擬服務註冊中心。")
        except json.JSONDecodeError:
            log.error("無法解析 MOCK_SERVICE_REGISTRY 環境變數，將回退到檔案。")
            registry = None

    # 如果沒有從環境變數成功載入，則從檔案讀取
    if registry is None:
        if not SERVICE_REGISTRY_FILE.exists():
            log.error(f"服務註冊檔案不存在: {SERVICE_REGISTRY_FILE}")
            return None
        try:
            with open(SERVICE_REGISTRY_FILE, 'r', encoding='utf-8') as f:
                registry = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            log.error(f"讀取或解析服務註冊檔案 '{SERVICE_REGISTRY_FILE}' 時發生錯誤: {e}")
            return None

    try:
        service_info = registry.get(service_name)
        if not service_info or "port" not in service_info:
            log.error(f"在註冊中心找不到服務 '{service_name}' 的有效配置。")
            return None

        port = service_info["port"]
        url = f"http://127.0.0.1:{port}"
        log.info(f"為服務 '{service_name}' 發現的 URL: {url}")
        return url
    except Exception as e:
        log.error(f"查詢服務 '{service_name}' 時發生未預期錯誤: {e}", exc_info=True)
        return None