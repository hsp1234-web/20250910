# src/api/routes/bond_service_proxy.py
import httpx
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

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


@router.get("/charts/{chart_id}")
async def proxy_chart_data_request(chart_id: str, request: Request):
    """
    代理對 bond_data_service 的**JSON數據**請求。
    主要用於獲取動態圖表（如壓力指數MACD）所需的數據。
    """
    try:
        base_url = await get_bond_service_url()
        query_params = request.url.query
        data_url = f"{base_url}/charts/{chart_id}?{query_params}" if query_params else f"{base_url}/charts/{chart_id}"

        async with httpx.AsyncClient() as client:
            response = await client.get(data_url, timeout=30.0)
            response.raise_for_status()
            # 這裡我們期望的是 JSON，所以直接回傳 JSONResponse
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type='application/json'
            )
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get('detail', e.response.text)
        except json.JSONDecodeError:
            detail = e.response.text
        raise HTTPException(status_code=e.response.status_code, detail=f"債券資料服務(數據)錯誤: {detail}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"無法連線至債券資料服務(數據): {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"代理數據請求時發生內部錯誤: {e}")


@router.get("/data/{chart_id}")
async def proxy_dynamic_data_request(chart_id: str, request: Request):
    """
    代理對 bond_data_service 的**動態圖表 JSON 數據**請求。
    這是為了支援 V2.1 前端動態渲染所有圖表的新架構。
    """
    try:
        base_url = await get_bond_service_url()
        query_params = request.url.query
        data_url = f"{base_url}/data/{chart_id}?{query_params}" if query_params else f"{base_url}/data/{chart_id}"

        async with httpx.AsyncClient() as client:
            response = await client.get(data_url, timeout=30.0)
            response.raise_for_status()
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type='application/json'
            )
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get('detail', e.response.text)
        except json.JSONDecodeError:
            detail = e.response.text
        raise HTTPException(status_code=e.response.status_code, detail=f"債券資料服務(動態數據)錯誤: {detail}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"無法連線至債券資料服務(動態數據): {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"代理動態數據請求時發生內部錯誤: {e}")
