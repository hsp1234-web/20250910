# src/api/routes/page10_test.py
# 這是一個 API 閘道，用於將前端請求代理到後端的微服務。
import json
import logging
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException, Body, Request
from pydantic import BaseModel, Field
from typing import Any, Optional

# --- 設定 ---
log = logging.getLogger(__name__)
router = APIRouter()
SERVICE_REGISTRY_FILE = Path("/tmp/service_registry.json")

# --- 輔助函式 ---
def get_service_url(service_name: str) -> str:
    """從服務註冊檔案中讀取微服務的 URL。"""
    if not SERVICE_REGISTRY_FILE.exists():
        raise HTTPException(status_code=503, detail="服務註冊尚不可用，請稍後再試。")

    with open(SERVICE_REGISTRY_FILE, 'r') as f:
        registry = json.load(f)

    service_info = registry.get(service_name)
    if not service_info or service_info.get("status") != "running" or not service_info.get("port"):
        raise HTTPException(status_code=503, detail=f"服務 '{service_name}' 目前不可用或未註冊。")

    return f"http://127.0.0.1:{service_info['port']}"

# --- Pydantic 模型 (與前端同步) ---
class KeyProxyModel(BaseModel):
    api_key: str
    name: Optional[str] = None

# --- API 端點 ---

@router.get("/keys", summary="從金鑰服務獲取所有金鑰")
async def get_keys_from_service():
    """
    代理請求到 key_service 以獲取所有金鑰。
    """
    try:
        service_url = get_service_url("key_service")
        # 注意：端點路徑要與微服務中的路徑匹配
        response = requests.get(f"{service_url}/api/keys", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        log.error(f"代理 GET /keys 請求到 key_service 時發生錯誤: {e}")
        raise HTTPException(status_code=504, detail=f"無法連線到後端金鑰服務: {e}")
    except HTTPException as e:
        raise e # 重新拋出我們自己產生的 HTTP 錯誤
    except Exception as e:
        log.error(f"處理 GET /keys 代理時發生未知錯誤: {e}")
        raise HTTPException(status_code=500, detail="處理代理請求時發生未知錯誤。")

@router.post("/keys", summary="透過金鑰服務新增金鑰")
async def add_key_via_service(payload: KeyProxyModel):
    """
    代理請求到 key_service 以新增一個金鑰。
    """
    try:
        service_url = get_service_url("key_service")
        response = requests.post(
            f"{service_url}/api/keys",
            json=payload.dict(),
            timeout=30 # 新增金鑰可能需要驗證，因此超時時間長一點
        )
        # 即使後端服務回傳 4xx 或 5xx，我們也應該將其轉發
        if response.status_code >= 400:
             # 嘗試解析後端服務的錯誤訊息
            try:
                error_detail = response.json()
            except json.JSONDecodeError:
                error_detail = response.text
            raise HTTPException(status_code=response.status_code, detail=error_detail)

        return response.json()
    except requests.exceptions.RequestException as e:
        log.error(f"代理 POST /keys 請求到 key_service 時發生錯誤: {e}")
        raise HTTPException(status_code=504, detail=f"無法連線到後端金鑰服務: {e}")
    except HTTPException as e:
        raise e
    except Exception as e:
        log.error(f"處理 POST /keys 代理時發生未知錯誤: {e}")
        raise HTTPException(status_code=500, detail="處理代理請求時發生未知錯誤。")

# 可以為刪除操作也新增一個代理端點
@router.delete("/keys/{key_hash}", summary="透過金鑰服務刪除金鑰")
async def delete_key_via_service(key_hash: str):
    try:
        service_url = get_service_url("key_service")
        response = requests.delete(f"{service_url}/api/keys/{key_hash}", timeout=10)
        if response.status_code >= 400:
            try:
                error_detail = response.json()
            except json.JSONDecodeError:
                error_detail = response.text
            raise HTTPException(status_code=response.status_code, detail=error_detail)
        return response.json()
    except requests.exceptions.RequestException as e:
        log.error(f"代理 DELETE /keys/{key_hash} 請求到 key_service 時發生錯誤: {e}")
        raise HTTPException(status_code=504, detail=f"無法連線到後端金鑰服務: {e}")
    except HTTPException as e:
        raise e
    except Exception as e:
        log.error(f"處理 DELETE /keys 代理時發生未知錯誤: {e}")
        raise HTTPException(status_code=500, detail="處理代理請求時發生未知錯誤。")
