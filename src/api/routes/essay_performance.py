# src/api/routes/essay_performance.py
import httpx
from fastapi import APIRouter, Request, HTTPException, Body, Depends
from pydantic import BaseModel
import logging
import json

# --- 日誌設定 ---
log = logging.getLogger('api_gateway')

# --- FastAPI 路由器 ---
router = APIRouter(
    prefix="/api/essay_performance",
    tags=["Essay Performance"],
)

# --- 微服務配置 ---
# 在生產環境中，這個地址可能來自配置檔案或服務發現機制
ESSAY_INGESTION_SERVICE_URL = "http://localhost:8001"

# --- 共用 HTTP 客戶端 ---
# 使用 Depends 來管理 httpx.AsyncClient 的生命週期，以實現連線池和更高效能
async def get_http_client():
    async with httpx.AsyncClient() as client:
        yield client

# --- 資料模型 ---
# 這個模型與前端的請求 body 匹配
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
    """
    target_url = f"{ESSAY_INGESTION_SERVICE_URL}/ingest"
    log.info(f"代理請求至: {target_url}")

    try:
        # 將收到的請求 body 轉換為 JSON，並轉發給微服務
        response = await client.post(
            target_url,
            json=request_body.model_dump(),
            timeout=30.0  # 設定一個合理的超時時間
        )

        # 檢查從微服務收到的回應狀態碼
        response.raise_for_status()

        # 將微服務的回應直接回傳給前端
        return response.json()

    except httpx.HTTPStatusError as e:
        # 如果微服務回傳錯誤 (e.g., 4xx, 5xx)，則將其錯誤資訊轉發給前端
        log.error(f"微服務回傳錯誤狀態碼 {e.response.status_code}: {e.response.text}")
        # 嘗試解析微服務的錯誤詳情
        try:
            detail = e.response.json()
        except json.JSONDecodeError:
            detail = e.response.text
        raise HTTPException(status_code=e.response.status_code, detail=detail)

    except httpx.RequestError as e:
        # 如果無法連線到微服務 (e.g., 連線被拒、超時)
        log.error(f"無法連線至小作文擷取服務: {e}")
        raise HTTPException(
            status_code=503,  # 503 Service Unavailable
            detail="後端擷取服務目前無法使用，請稍後再試。"
        )
    except Exception as e:
        # 捕捉其他未預期的錯誤
        log.error(f"代理請求時發生未預期錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="代理請求時發生內部錯誤。")