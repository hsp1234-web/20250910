import logging
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import pandas as pd
from io import BytesIO

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from tools.url_extractor import parse_chat_log
# V4 優化：移除舊的資料庫連線方式
# from db.database import get_db_connection
from fastapi import Depends
from db.client import DBClient
from ..dependencies import get_db

# --- 常數與設定 ---
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()

class UrlExtractionRequest(BaseModel):
    text: str

# --- HTML 頁面路由 ---
@router.get("/page1/ingestion", response_class=HTMLResponse)
async def get_ingestion_page(request: Request):
    return templates.TemplateResponse("page1_sub_ingestion.html", {"request": request})

@router.get("/page1/overview", response_class=HTMLResponse)
async def get_overview_page(request: Request):
    return templates.TemplateResponse("page1_sub_overview.html", {"request": request})

@router.get("/page1/export", response_class=HTMLResponse)
async def get_export_page(request: Request):
    return templates.TemplateResponse("page1_sub_export.html", {"request": request})

import requests
import json

# --- V7 代理設定 ---
SERVICE_REGISTRY_FILE = Path("/tmp/service_registry.json")
INGESTION_SERVICE_NAME = "ingestion_service"

def get_service_url(service_name: str) -> str:
    if not SERVICE_REGISTRY_FILE.exists():
        raise HTTPException(status_code=503, detail="服務註冊尚不可用。")
    try:
        with open(SERVICE_REGISTRY_FILE, 'r') as f:
            registry = json.load(f)
        service_info = registry.get(service_name)
        if not service_info or service_info.get("status") != "running":
            raise HTTPException(status_code=503, detail=f"服務 '{service_name}' 目前不可用。")
        return f"http://127.0.0.1:{service_info['port']}"
    except Exception:
        raise HTTPException(status_code=503, detail="無法讀取或解析服務註冊表。")

async def proxy_request_with_query_params(method: str, endpoint: str, request: Request, timeout: int = 20):
    try:
        service_url = get_service_url(INGESTION_SERVICE_NAME)
        # 包含查詢參數
        full_url = f"{service_url}{endpoint}"
        if request.url.query:
            full_url += f"?{request.url.query}"

        json_payload = None
        if method in ["POST", "PUT"]:
            try:
                json_payload = await request.json()
            except json.JSONDecodeError:
                pass

        log.info(f"代理請求: {method} {full_url}")
        response = requests.request(
            method=method,
            url=full_url,
            json=json_payload,
            headers={key: value for key, value in request.headers.items() if key.lower() not in ['host', 'content-length', 'content-type']},
            timeout=timeout,
            stream=True # 使用流式傳輸以處理檔案下載
        )

        # 直接將後端服務的回應 (包括 headers 和 content) 作為串流回傳
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers)
        )

    except requests.exceptions.RequestException as e:
        log.error(f"代理請求到 {INGESTION_SERVICE_NAME} 時發生網路錯誤: {e}")
        raise HTTPException(status_code=504, detail=f"無法連線到後端服務 '{INGESTION_SERVICE_NAME}'。")
    except Exception as e:
        log.error(f"處理代理請求時發生未知錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="處理代理請求時發生未知伺服器錯誤。")

# --- API 端點 (V7 重構後) ---
@router.post("/api/page1/extract_urls", status_code=200)
async def extract_urls_endpoint(request: Request):
    """(V7 代理) 轉發請求至 ingestion_service。"""
    return await proxy_request_with_query_params("POST", "/api/page1/extract_urls", request)

@router.get("/api/page1/overview_data")
async def get_overview_data(request: Request):
    """(V7 代理) 轉發請求至 ingestion_service。"""
    return await proxy_request_with_query_params("GET", "/api/page1/overview_data", request)

@router.get("/api/page1/export")
async def export_data(request: Request):
    """(V7 代理) 轉發請求至 ingestion_service，處理檔案下載。"""
    return await proxy_request_with_query_params("GET", "/api/page1/export", request)
