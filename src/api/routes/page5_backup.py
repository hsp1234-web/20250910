# src/api/routes/page5_backup.py
# API 閘道 - 備份服務代理
# -------------------------------------------------
# 說明：
# (V7 重構後) 這個檔案作為一個純粹的代理（Proxy）。
# 它接收來自前端的 /api/backup/start_backup 請求，
# 並將其轉發給後端獨立的 `backup_service` 微服務。
# 自身不再包含任何業務邏輯。
# -------------------------------------------------
import json
import logging
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException, Request

# --- 設定 ---
log = logging.getLogger(__name__)
router = APIRouter()
SERVICE_REGISTRY_FILE = Path("/tmp/service_registry.json")
BACKUP_SERVICE_NAME = "backup_service"

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
        service_url = get_service_url(BACKUP_SERVICE_NAME)
        url = f"{service_url}{endpoint}"

        log.info(f"代理請求: {method} {url}")
        response = requests.request(
            method=method,
            url=url,
            headers={key: value for key, value in request.headers.items() if key.lower() not in ['host', 'content-length']},
            timeout=timeout
        )

        if response.status_code >= 400:
            try:
                error_detail = response.json()
            except json.JSONDecodeError:
                error_detail = response.text
            raise HTTPException(status_code=response.status_code, detail=error_detail)

        return response.json()

    except requests.exceptions.Timeout:
        log.error(f"代理請求到 {BACKUP_SERVICE_NAME} 超時 (timeout={timeout}s)")
        raise HTTPException(status_code=504, detail=f"請求後端服務 '{BACKUP_SERVICE_NAME}' 超時。")
    except requests.exceptions.RequestException as e:
        log.error(f"代理請求到 {BACKUP_SERVICE_NAME} 時發生網路錯誤: {e}")
        raise HTTPException(status_code=504, detail=f"無法連線到後端服務 '{BACKUP_SERVICE_NAME}'。")
    except HTTPException as e:
        raise e
    except Exception as e:
        log.error(f"處理代理請求時發生未知錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="處理代理請求時發生未知伺服器錯誤。")


# --- API 端點 ---
@router.post("/start_backup")
async def start_backup(request: Request):
    """
    (V7 重構後) 代理請求到備份服務以觸發背景備份任務。
    """
    log.info("API 閘道：收到啟動備份的請求，將轉發至 backup_service。")
    # 轉發時，端點路徑也應與目標服務一致
    return await proxy_request("POST", "/start_backup", request)
