# src/api/routes/bond_service_proxy.py
import httpx
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

SERVICE_REGISTRY_FILE = Path("/tmp/service_registry.json")

async def get_bond_service_url() -> str:
    """從服務註冊中心獲取 bond_data_service 的基礎 URL。"""
    if not SERVICE_REGISTRY_FILE.exists():
        raise HTTPException(status_code=503, detail="服務註冊中心不可用。")

    with open(SERVICE_REGISTRY_FILE, 'r') as f:
        registry = json.load(f)

    service_info = registry.get('bond_data_service')
    if not service_info or not service_info.get('port'):
        raise HTTPException(status_code=404, detail="在註冊中心找不到債券資料服務。")

    port = service_info['port']
    return f"http://127.0.0.1:{port}"

@router.get("/chart/{indicator_id}")
async def proxy_chart_request(indicator_id: str):
    """
    代理對 bond_data_service 的圖表請求。
    """
    try:
        base_url = await get_bond_service_url()
        chart_url = f"{base_url}/chart/{indicator_id}"

        async with httpx.AsyncClient() as client:
            # 使用 stream=True 來準備串流回應
            # 增加超時時間，因為圖表生成可能需要一些時間
            req = client.build_request("GET", chart_url, timeout=60.0)
            r = await client.send(req, stream=True)

            # 如果下游服務回傳錯誤，也將其轉發
            r.raise_for_status()

            # 將下游服務的回應串流回傳給原始請求者
            return StreamingResponse(
                r.aiter_bytes(),
                status_code=r.status_code,
                media_type=r.headers.get("content-type")
            )

    except httpx.HTTPStatusError as e:
        # 如果下游服務回傳 4xx 或 5xx 錯誤
        # 嘗試讀取錯誤回應的內容
        try:
            detail_json = e.response.json()
            detail = detail_json.get('detail', e.response.text)
        except json.JSONDecodeError:
            detail = e.response.text
        raise HTTPException(status_code=e.response.status_code, detail=f"債券資料服務錯誤: {detail}")
    except httpx.RequestError as e:
        # 如果請求本身失敗 (例如，無法連線)
        raise HTTPException(status_code=502, detail=f"無法連線至債券資料服務: {e}")
    except Exception as e:
        # 處理其他潛在錯誤，如讀取註冊檔失敗
        raise HTTPException(status_code=500, detail=f"代理請求時發生內部錯誤: {e}")
