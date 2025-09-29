# src/api/routes/key_master_proxy.py
import httpx
from fastapi import APIRouter, Request, Response, HTTPException
import logging

# 專門為此代理建立一個日誌記錄器
log = logging.getLogger('key_master_proxy')

# 建立一個 APIRouter 實例
router = APIRouter()

# key_master_service 微服務的目標位址
KEY_MASTER_SERVICE_URL = "http://127.0.0.1:8008"

# 建立一個可重複使用的 httpx 非同步客戶端
# 透過 FastAPI 的生命週期事件來管理客戶端的連線與關閉
@router.on_event("startup")
async def startup_event():
    """在應用程式啟動時，初始化 httpx 客戶端"""
    router.state.client = httpx.AsyncClient(base_url=KEY_MASTER_SERVICE_URL)
    log.info(f"Key Master Service 的反向代理客戶端已啟動，目標為 {KEY_MASTER_SERVICE_URL}")

@router.on_event("shutdown")
async def shutdown_event():
    """在應用程式關閉時，優雅地關閉 httpx 客戶端"""
    await router.state.client.aclose()
    log.info("Key Master Service 的反向代理客戶端已關閉。")

# 建立一個可以捕捉所有請求路徑的反向代理端點
# {path:path} 會捕捉所有在 /key-api/ 後面的路徑
@router.api_route("/key-api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def reverse_proxy(request: Request, path: str):
    """
    此端點作為 key_master_service 的反向代理。
    它會將所有 /key-api/ 的請求轉發到 http://127.0.0.1:8008/{path}
    """
    try:
        client: httpx.AsyncClient = router.state.client

        # 建立目標 URL，將前端請求的路徑和查詢參數都附加到目標服務的 URL 上
        url = httpx.URL(path=f"/{path}", query=request.url.query.encode("utf-8"))

        # 準備請求標頭，並修正 Host 標頭
        headers = dict(request.headers)
        headers["host"] = client.base_url.host

        # 讀取請求的 body
        body = await request.body()

        # 建立轉發請求
        rp_req = client.build_request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
            timeout=30.0  # 設定 30 秒超時
        )

        # 發送請求並串流回應
        rp_resp = await client.send(rp_req, stream=True)

        # 將目標服務的回應直接回傳給原始客戶端
        return Response(
            content=await rp_resp.aread(),
            status_code=rp_resp.status_code,
            headers=dict(rp_resp.headers)
        )

    except httpx.ConnectError as e:
        log.error(f"無法連接到 Key Master Service ({KEY_MASTER_SERVICE_URL}): {e}")
        raise HTTPException(
            status_code=503, # Service Unavailable
            detail=f"無法連接到後端金鑰服務，請確認該服務是否正在運行。"
        )
    except Exception as e:
        log.error(f"反向代理發生未預期的錯誤: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"處理請求時發生內部錯誤。"
        )