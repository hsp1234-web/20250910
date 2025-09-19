# src/api/routes/page6_keys.py
# API 閘道 - 金鑰與設定管理代理
# -------------------------------------------------
# 說明：
# 這個檔案現在作為一個純粹的代理（Proxy）。
# 它接收來自前端的請求，並將它們轉發給後端獨立的 `key_service` 微服務。
# 自身不再包含任何業務邏輯。
# -------------------------------------------------
import json
import logging
from pathlib import Path
from typing import Optional, Any, Dict

import requests
from fastapi import APIRouter, HTTPException, Request

# --- 設定 ---
log = logging.getLogger(__name__)
router = APIRouter()
SERVICE_REGISTRY_FILE = Path("/tmp/service_registry.json")
KEY_SERVICE_NAME = "key_service"

# --- 輔助函式 ---
def get_service_url(service_name: str) -> str:
    """從服務註冊檔案中讀取微服務的 URL。"""
    if not SERVICE_REGISTRY_FILE.exists():
        raise HTTPException(status_code=503, detail="服務註冊尚不可用 (註冊表檔案不存在)。")
    try:
        with open(SERVICE_REGISTRY_FILE, 'r') as f:
            registry = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        raise HTTPException(status_code=503, detail="無法讀取或解析服務註冊表。")

    service_info = registry.get(service_name)
    if not service_info or service_info.get("status") != "running" or not service_info.get("port"):
        raise HTTPException(status_code=503, detail=f"服務 '{service_name}' 目前不可用或未正確註冊。")

    return f"http://127.0.0.1:{service_info['port']}"

async def proxy_request(method: str, endpoint: str, request: Request, timeout: int = 15):
    """通用請求代理函式。"""
    try:
        service_url = get_service_url(KEY_SERVICE_NAME)
        url = f"{service_url}{endpoint}"

        json_payload = None
        if method in ["POST", "PUT"]:
            try:
                json_payload = await request.json()
            except json.JSONDecodeError:
                # 如果請求 body 不是 JSON，則作為空 payload 處理
                pass

        log.info(f"代理請求: {method} {url}")
        response = requests.request(
            method=method,
            url=url,
            json=json_payload,
            headers={key: value for key, value in request.headers.items() if key.lower() not in ['host', 'content-length']},
            timeout=timeout
        )

        # 轉發後端服務的回應，包括狀態碼和內容
        if response.status_code >= 400:
            try:
                error_detail = response.json()
            except json.JSONDecodeError:
                error_detail = response.text
            raise HTTPException(status_code=response.status_code, detail=error_detail)

        return response.json()

    except requests.exceptions.Timeout:
        log.error(f"代理請求到 {KEY_SERVICE_NAME} 超時 (timeout={timeout}s)")
        raise HTTPException(status_code=504, detail=f"請求後端服務 '{KEY_SERVICE_NAME}' 超時。")
    except requests.exceptions.RequestException as e:
        log.error(f"代理請求到 {KEY_SERVICE_NAME} 時發生網路錯誤: {e}")
        raise HTTPException(status_code=504, detail=f"無法連線到後端服務 '{KEY_SERVICE_NAME}'。")
    except HTTPException as e:
        # 重新拋出我們自己或後端服務產生的 HTTP 錯誤
        raise e
    except Exception as e:
        log.error(f"處理代理請求時發生未知錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="處理代理請求時發生未知伺服器錯誤。")

# --- API 端點 ---
# 每個端點現在都呼叫通用的代理函式

@router.get("", summary="獲取所有金鑰的狀態")
async def get_keys_status(request: Request):
    return await proxy_request("GET", "/api/keys", request)

@router.post("", summary="新增並驗證一個 API 金鑰")
async def add_new_key(request: Request):
    return await proxy_request("POST", "/api/keys", request, timeout=45) # 驗證金鑰可能耗時較長

@router.delete("/{key_hash}", summary="刪除指定的 API 金鑰")
async def remove_key(key_hash: str, request: Request):
    return await proxy_request("DELETE", f"/api/keys/{key_hash}", request)

@router.post("/validate", summary="重新驗證所有金鑰")
async def validate_all_stored_keys(request: Request):
    return await proxy_request("POST", "/api/keys/validate", request, timeout=180) # 驗證所有金鑰非常耗時

@router.post("/load_from_authorized_source", summary="從授權來源（環境變數）載入金鑰")
async def load_keys_from_env(request: Request):
    return await proxy_request("POST", "/api/keys/load_from_authorized_source", request)

@router.get("/models", summary="獲取所有可用的 AI 模型")
async def get_available_models(request: Request):
    return await proxy_request("GET", "/api/keys/models", request)

@router.post("/test", summary="測試一個 API 金鑰的有效性")
async def test_api_key(request: Request):
    return await proxy_request("POST", "/api/keys/test", request)

@router.get("/config/{key}", summary="獲取指定的設定值")
async def get_config_value_api(key: str, request: Request):
    return await proxy_request("GET", f"/api/keys/config/{key}", request)

@router.post("/config/{key}", summary="更新指定的設定值")
async def update_config_value_api(key: str, request: Request):
    return await proxy_request("POST", f"/api/keys/config/{key}", request)
