# src/api/routes/bond_service_proxy.py
import httpx
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, HTMLResponse

router = APIRouter()
page_router = APIRouter() # 新增一個用於代理頁面的路由器

@page_router.get("/interactive_chart", response_class=HTMLResponse, include_in_schema=False)
async def proxy_interactive_chart_page(request: Request):
    """
    代理對 bond_data_service 的互動圖表頁面請求。
    這個路由沒有 /api 前綴，直接從根路徑提供頁面。
    """
    try:
        base_url = await get_bond_service_url()
        query_params = request.url.query
        target_url = f"{base_url}/interactive_chart?{query_params}" if query_params else f"{base_url}/interactive_chart"

        async with httpx.AsyncClient() as client:
            response = await client.get(target_url, timeout=10.0)
            response.raise_for_status()
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
    except httpx.HTTPStatusError as e:
        detail = e.response.text
        raise HTTPException(status_code=e.response.status_code, detail=f"債券資料服務(頁面)錯誤: {detail}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"無法連線至債券資料服務(頁面): {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"代理互動圖表頁面時發生內部錯誤: {e}")

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

@router.get("/health")
async def proxy_health_check(request: Request):
    """
    代理對 bond_data_service 的健康檢查請求。
    """
    try:
        base_url = await get_bond_service_url()
        health_url = f"{base_url}/health"

        async with httpx.AsyncClient() as client:
            response = await client.get(health_url, timeout=5.0) # 使用較短的超時
            response.raise_for_status()
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type='application/json'
            )
    except httpx.RequestError:
        # 如果請求失敗（例如服務尚未啟動），回傳一個清晰的「服務不可用」狀態
        raise HTTPException(status_code=503, detail="債券資料服務目前無法連線。")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"代理健康檢查時發生內部錯誤: {e}")


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


@router.get("/dashboard_data")
async def proxy_dashboard_data(request: Request):
    """
    代理對 bond_data_service 的儀表板數據請求。
    這個端點專門處理來自前端的 /dashboard_data 請求，
    並將其直接轉發到下游服務的同名端點。
    """
    try:
        base_url = await get_bond_service_url()
        query_params = request.url.query
        # 將請求轉發到 bond_data_service 的 /api/bond_service/dashboard_data 端點
        data_url = f"{base_url}/api/bond_service/dashboard_data?{query_params}" if query_params else f"{base_url}/api/bond_service/dashboard_data"

        async with httpx.AsyncClient() as client:
            response = await client.get(data_url, timeout=30.0)
            # 直接回傳下游服務的內容、狀態碼和媒體類型
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
    except httpx.HTTPStatusError as e:
        # 如果下游服務回傳錯誤，也將其轉發
        try:
            detail = e.response.json().get('detail', e.response.text)
        except json.JSONDecodeError:
            detail = e.response.text
        raise HTTPException(status_code=e.response.status_code, detail=f"債券資料服務(儀表板)錯誤: {detail}")
    except httpx.RequestError as e:
        # 處理網路連線問題
        raise HTTPException(status_code=502, detail=f"無法連線至債券資料服務(儀表板): {e}")
    except Exception as e:
        # 處理代理伺服器自身的問題
        raise HTTPException(status_code=500, detail=f"代理儀表板數據請求時發生內部錯誤: {e}")

@router.post("/trigger_update")
async def proxy_trigger_update(request: Request):
    """
    代理對 bond_data_service 的資料更新觸發請求 (POST)。
    這是修復流程的核心，它將前端的觸發請求轉發到後端資料服務。
    """
    try:
        base_url = await get_bond_service_url()
        target_url = f"{base_url}/api/trigger_update"

        # 獲取前端發來的 JSON 內容
        request_body = await request.json()

        async with httpx.AsyncClient() as client:
            # 將 POST 請求連同 JSON 內容一起轉發
            # 設定一個較長的超時時間，因為這一步可能涉及大量的網路抓取
            response = await client.post(target_url, json=request_body, timeout=120.0)

            # 將下游服務的回應直接回傳給前端
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )

    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get('detail', e.response.text)
        except json.JSONDecodeError:
            detail = e.response.text
        raise HTTPException(status_code=e.response.status_code, detail=f"債券資料服務(觸發更新)錯誤: {detail}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"無法連線至債券資料服務(觸發更新): {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"代理觸發更新請求時發生內部錯誤: {e}")
