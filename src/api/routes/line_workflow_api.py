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
    prefix="/api/workflows",
    tags=["Workflows"],
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
# (Jules @ 2025-10-15) 修正：直接將 DBClient 作為依賴項，FastAPI 會自動處理實例化
# 這也使得在測試中覆寫它變得更直接
def get_db_client():
    """提供一個 DBClient 的共享實例。"""
    return DBClient()

# --- 資料模型 ---
from typing import List, Dict, Any

class IngestRequest(BaseModel):
    text: str

class WorkflowItem(BaseModel):
    id: int
    url: str

class CreateWorkflowRequest(BaseModel):
    name: str
    items: List[WorkflowItem]

# --- API 端點 (代理模式) ---
@router.post("/ingest_text", summary="代理文字擷取請求至 line_parser_service")
async def proxy_ingest_text(
    request_body: IngestRequest,
    client: httpx.AsyncClient = Depends(get_http_client),
    db_client: DBClient = Depends(get_db_client) # 新增 DBClient 依賴
):
    """
    代理端點，將來自 LINE 的聊天紀錄文字轉發至後端的 line_parser_service。
    """
    try:
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

# --- 新的 API 端點 ---

@router.post("/create_from_items", summary="從選定項目建立一個新的工作流")
async def create_workflow_from_items(
    request: CreateWorkflowRequest,
    db_client: DBClient = Depends(get_db_client)
):
    """
    接收一個工作流名稱和一個項目列表，然後：
    1. 建立一個新的工作流。
    2. 為列表中的每一個項目建立一個對應的步驟。
    返回新建立的工作流 ID。
    """
    try:
        # 1. 建立工作流
        workflow = db_client.create_workflow(request.name)
        workflow_id = workflow["id"]

        # 2. 為每個項目新增步驟
        for item in request.items:
            step_payload = {
                "command": "DOWNLOAD_AND_EXTRACT",
                "parameters": {
                    "url": item.url,
                    "source_url_id": item.id
                }
            }
            db_client.add_workflow_step(workflow_id, step_payload)

        return {"workflow_id": workflow_id, "message": f"成功建立工作流 #{workflow_id} 並新增 {len(request.items)} 個步驟。"}
    except Exception as e:
        log.error(f"從項目建立工作流時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="建立工作流時發生內部伺服器錯誤。")


@router.get("/latest", summary="獲取最新建立的工作流")
async def get_latest_workflow(db_client: DBClient = Depends(get_db_client)):
    """
    檢索最新的一個工作流及其所有步驟的詳細資訊。
    這是工作流編輯器頁面的主要資料來源。
    """
    try:
        workflow = db_client.get_latest_workflow()
        if not workflow:
            raise HTTPException(status_code=404, detail="尚未建立任何工作流。")

        steps = db_client.get_workflow_steps(workflow["id"])
        return {"workflow": workflow, "steps": steps}
    except HTTPException as e:
        raise e # 重新引發已知的 HTTP 錯誤
    except Exception as e:
        log.error(f"獲取最新工作流時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="讀取最新工作流時發生內部錯誤。")


@router.post("/{workflow_id}/reset", summary="重置指定工作流的狀態")
async def reset_workflow(workflow_id: int, db_client: DBClient = Depends(get_db_client)):
    """
    將一個已完成或失敗的工作流狀態重置為 'pending'，以便可以重新執行。
    """
    try:
        db_client.reset_workflow_status(workflow_id)
        return {"message": f"工作流 #{workflow_id} 已成功重置。"}
    except ValueError as e:
        # 捕獲由 DBClient 引發的、表示找不到 ID 的錯誤
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error(f"重置工作流 #{workflow_id} 時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重置工作流時發生內部錯誤。")


# (Jules @ 2025-10-15) 根據需求，舊的 get_all_workflows 端點已被移除。

@router.get("/{workflow_id}/line_status", summary="獲取工作流中所有 LINE 項目的精細化狀態")
async def get_workflow_line_item_status(
    workflow_id: int,
    db_client: DBClient = Depends(get_db_client)
):
    """
    (Jules @ 2025-10-14) 新增的端點，用於獲取工作流中每個步驟對應項目的詳細狀態。
    """
    workflow = db_client.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="找不到指定的工作流。")

    steps = db_client.get_workflow_steps(workflow_id)

    detailed_statuses = []
    for step in steps:
        source_url_id = step.get("parameters", {}).get("source_url_id")
        if not source_url_id:
            continue

        item_details = db_client.get_url_by_id(source_url_id)
        if not item_details:
            continue

        detailed_statuses.append({
            "step_id": step["id"],
            "source_url_id": source_url_id,
            "status_download": item_details.get("status_download", "N/A"),
            "status_extraction": item_details.get("status_extraction", "N/A"),
            "status_ocr": item_details.get("status_ocr", "N/A"),
            "status_ai_summary": item_details.get("status_ai_summary", "N/A"),
            "overall_status": item_details.get("status", "N/A"),
            "last_error": item_details.get("last_error_details")
        })

    return {
        "workflow_id": workflow_id,
        "workflow_status": workflow.get("status"),
        "steps": detailed_statuses
    }