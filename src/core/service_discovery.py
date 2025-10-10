import json
from pathlib import Path
import logging
from typing import Optional

# --- 日誌設定 ---
log = logging.getLogger(__name__)

# --- 常數定義 ---
SERVICE_REGISTRY_FILE = Path("/tmp/service_registry.json")

def get_service_url(service_name: str) -> Optional[str]:
    """
    從服務註冊檔案中讀取指定服務的 URL。
    這是一個可重用的函式，供所有需要進行服務間通訊的模組使用。

    Args:
        service_name (str): 想要查詢的服務名稱 (例如 "llm_service")。

    Returns:
        Optional[str]: 服務的基底 URL (例如 "http://127.0.0.1:12345")，如果找不到或發生錯誤則回傳 None。
    """
    if not SERVICE_REGISTRY_FILE.exists():
        log.error(f"服務註冊檔案不存在: {SERVICE_REGISTRY_FILE}")
        return None

    try:
        with open(SERVICE_REGISTRY_FILE, 'r', encoding='utf-8') as f:
            registry = json.load(f)

        service_info = registry.get(service_name)
        if not service_info or "port" not in service_info:
            log.error(f"在註冊中心找不到服務 '{service_name}' 的有效配置。")
            return None

        port = service_info["port"]
        # 假設服務皆在本機上，透過 localhost 進行通訊
        url = f"http://127.0.0.1:{port}"
        log.info(f"為服務 '{service_name}' 發現的 URL: {url}")
        return url

    except (json.JSONDecodeError, IOError) as e:
        log.error(f"讀取或解析服務註冊檔案 '{SERVICE_REGISTRY_FILE}' 時發生錯誤: {e}")
        return None
    except Exception as e:
        log.error(f"查詢服務 '{service_name}' 時發生未預期錯誤: {e}", exc_info=True)
        return None