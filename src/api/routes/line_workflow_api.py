# src/api/routes/line_workflow_api.py
import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import logging
import json

# --- 專案內部模組匯入 ---
from src.db.client import DBClient
from src.core.service_discovery import get_service_url as get_service_url_from_core

# --- 日誌設定 ---
log = logging.getLogger('api_gateway')

# --- FastAPI 路由器 ---
router = APIRouter(
    prefix="/api/line",
    tags=["LINE Workflow"],
)

# --- 微服務配置 ---
SERVICE_NAME = "line_parser_service"

def get_service_url_wrapper(service_name: str) -> str:
    """
    一個包裝函式，呼叫核心服務發現模組並處理錯誤，將其轉換為適合 API 路由的 HTTPException。
    """
    url = get_service_url_from_core(service_name)
    if url is None:
        log.error(f"服務發現失敗: 無法為服務 '{service_name}' 找到 URL。")
        raise HTTPException(status_code=503, detail=f"服務 '{service_name}' 目前不可用或未註冊。")
    return url

# --- 共用 HTTP 客戶端 ---
async def get_http_client():
    async with httpx.AsyncClient() as client:
        yield client

# --- 依賴注入 ---
def get_db_client():
    """提供一個 DBClient 的共享實例。"""
    return DBClient()


# --- 資料模型 ---
class IngestRequest(BaseModel):
    text: str

# --- API 端點 (代理模式) ---
@router.post("/ingest_text", summary="代理文字擷取請求至 line_parser_service")
async def proxy_ingest_text(
    request_body: IngestRequest,
    client: httpx.AsyncClient = Depends(get_http_client)
):
    """
    代理端點，將來自 LINE 的聊天紀錄文字轉發至後端的 line_parser_service。
    """
    try:
        # 動態獲取微服務 URL
        service_base_url = get_service_url_wrapper(SERVICE_NAME)
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
        log.error(f"無法連線至服務 '{SERVICE_NAME}': {e}")
        raise HTTPException(
            status_code=503,
            detail="後端解析服務目前無法使用，請稍後再試。"
        )
    except Exception as e:
        log.error(f"代理請求時發生未預期錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="代理請求時發生內部錯誤。")


@router.get("/items", summary="獲取所有已匯入的 LINE 項目")
async def get_all_ingested_items(db_client: DBClient = Depends(get_db_client)):
    """
    從資料庫中獲取所有已透過 LINE 聊天紀錄匯入功能處理過的項目。
    """
    try:
        # 使用 get_filtered_urls()，不帶任何參數以獲取所有紀錄
        all_items = db_client.get_filtered_urls()
        # 預設按 ID 降序排序，讓最新的項目顯示在最前面
        if all_items:
            return sorted(all_items, key=lambda item: item.get('id', 0), reverse=True)
        return []
    except Exception as e:
        log.error(f"從資料庫獲取 LINE 項目時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法從資料庫讀取項目清單。")