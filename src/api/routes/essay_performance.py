# src/api/routes/essay_performance.py
import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import logging
import json
from pathlib import Path

# --- 日誌設定 ---
log = logging.getLogger('api_gateway')

# --- FastAPI 路由器 ---
router = APIRouter(
    prefix="/api/essay_performance",
    tags=["Essay Performance"],
)

# --- 微服務配置 ---
SERVICE_REGISTRY_FILE = Path("/tmp/service_registry.json")
SERVICE_NAME = "essay_ingestion_service"

def get_service_url(service_name: str) -> str:
    """
    從服務註冊檔案中讀取指定服務的 URL。
    """
    if not SERVICE_REGISTRY_FILE.exists():
        log.error(f"服務註冊檔案不存在: {SERVICE_REGISTRY_FILE}")
        raise HTTPException(status_code=503, detail="服務註冊中心不可用，無法路由請求。")

    try:
        with open(SERVICE_REGISTRY_FILE, 'r', encoding='utf-8') as f:
            registry = json.load(f)

        service_info = registry.get(service_name)
        if not service_info or "port" not in service_info:
            log.error(f"在註冊中心找不到服務 '{service_name}' 的有效配置。")
            raise HTTPException(status_code=503, detail=f"服務 '{service_name}' 未註冊或配置錯誤。")

        port = service_info["port"]
        # 在容器化環境中，服務之間通常透過 localhost 進行通訊
        return f"http://127.0.0.1:{port}"

    except (json.JSONDecodeError, IOError) as e:
        log.error(f"讀取或解析服務註冊檔案時發生錯誤: {e}")
        raise HTTPException(status_code=500, detail="讀取服務註冊中心時發生內部錯誤。")


# --- 共用 HTTP 客戶端 ---
async def get_http_client():
    async with httpx.AsyncClient() as client:
        yield client

# --- 資料模型 ---
class IngestRequest(BaseModel):
    text: str

# --- API 端點 (代理模式) ---
@router.post("/ingest_text")
async def proxy_ingest_text(
    request_body: IngestRequest,
    client: httpx.AsyncClient = Depends(get_http_client)
):
    """
    代理端點，將文字擷取請求轉發至後端的 essay_ingestion_service。
    (Jules @ 2025-10-07) 新增服務發現邏輯。
    """
    try:
        # 動態獲取微服務 URL
        service_base_url = get_service_url(SERVICE_NAME)
        target_url = f"{service_base_url}/ingest"
        log.info(f"代理請求至動態發現的 URL: {target_url}")

        response = await client.post(
            target_url,
            json=request_body.model_dump(),
            timeout=30.0
        )

        response.raise_for_status()
        return response.json()

    except HTTPException as e:
        # 重新引發由 get_service_url 產生的 HTTPExceptions
        raise e
    except httpx.HTTPStatusError as e:
        log.error(f"微服務回傳錯誤狀態碼 {e.response.status_code}: {e.response.text}")
        try:
            detail = e.response.json()
        except json.JSONDecodeError:
            detail = e.response.text
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except httpx.RequestError as e:
        log.error(f"無法連線至小作文擷取服務 '{SERVICE_NAME}': {e}")
        raise HTTPException(
            status_code=503,
            detail="後端擷取服務目前無法使用，請稍後再試。"
        )
    except Exception as e:
        log.error(f"代理請求時發生未預期錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="代理請求時發生內部錯誤。")