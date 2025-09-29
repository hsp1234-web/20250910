# src/api/routes/key_master_proxy.py
from fastapi import APIRouter, Request, Response
import httpx
import logging

# 取得日誌記錄器
log = logging.getLogger('key_master_proxy')

# 建立一個新的路由器
router = APIRouter()

# 後端 key_master_service 的位址
KEY_MASTER_SERVICE_URL = "http://127.0.0.1:8008"

# 建立一個可重複使用的 httpx.AsyncClient 實例
# 這樣可以利用連線池，提升效能
client = httpx.AsyncClient(base_url=KEY_MASTER_SERVICE_URL)

@router.api_route("/key-api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def reverse_proxy(request: Request, path: str):
    """
    一個反向代理端點，將所有來自 /key-api/ 的請求轉發到 key_master_service。
    """
    # 組合目標 URL
    # 從 request 中獲取完整的路徑，包括查詢參數
    full_path = f"/{path}"
    if request.query_params:
        full_path += f"?{request.query_params}"

    log.info(f"代理請求至 Key Master: {request.method} {full_path}")

    # 複製請求標頭，但排除 'host' 標頭，讓 httpx 自動處理
    headers = {key: value for key, value in request.headers.items() if key.lower() != 'host'}

    # 讀取請求內文
    body = await request.body()

    try:
        # 使用 httpx 發送請求到後端服務
        # 注意：我們直接將 `request.query_params` 傳給 `params`，而不是手動附加到 url 上
        rp_resp = await client.request(
            method=request.method,
            url=f"/{path}", # URL 路徑部分不應包含查詢字串
            headers=headers,
            content=body,
            params=request.query_params, # httpx 會自動處理查詢參數
            timeout=30.0  # 設定 30 秒超時
        )

        # 建立一個 FastAPI 回應，並複製後端服務的回應內容、狀態碼和標頭
        # 排除 'content-encoding' 和 'transfer-encoding'，讓 FastAPI 自動處理壓縮
        response_headers = {
            key: value for key, value in rp_resp.headers.items()
            if key.lower() not in ('content-encoding', 'transfer-encoding', 'connection')
        }

        return Response(
            content=rp_resp.content,
            status_code=rp_resp.status_code,
            headers=response_headers
        )

    except httpx.RequestError as e:
        log.error(f"代理請求至 Key Master Service 時發生錯誤: {e}")
        return Response(
            content=f"無法連接至後端金鑰服務: {e}",
            status_code=503  # Service Unavailable
        )