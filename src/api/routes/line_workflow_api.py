# src/api/routes/line_workflow_api.py
import httpx
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, List
import logging
import json
import asyncio

# --- 專案內部模組匯入 ---
from src.core import workflow_manager
from src.core.service_discovery import get_service_url as get_service_url_from_core

# --- 日誌設定 ---
log = logging.getLogger(__name__)

# --- FastAPI 路由器 ---
router = APIRouter(
    prefix="/api/workflows",
    tags=["Workflows"],
)

# --- 微服務配置 ---
SERVICE_NAME = "line_parser_service"

# --- 資料模型 ---
class WorkflowCreateRequest(BaseModel):
    name: str

class WorkflowStepRequest(BaseModel):
    command: str
    parameters: Dict[str, Any]
    step_order: int

# --- 核心工作流執行邏輯 (背景任務) ---
async def run_workflow_in_background(workflow_id: str):
    """
    在背景執行的工作流處理函式，現在完全基於檔案系統。
    """
    log.info(f"背景工作流 #{workflow_id} 開始執行。")
    try:
        workflow_manager.update_workflow_status(workflow_id, 'running')
        log.info(f"工作流 #{workflow_id} 狀態已更新為 'running'。")

        steps = workflow_manager.get_workflow_steps(workflow_id)
        if not steps:
            log.warning(f"工作流 #{workflow_id} 沒有任何步驟，即將結束。")
            workflow_manager.update_workflow_status(workflow_id, 'completed')
            return

        has_errors = False
        service_base_url = get_service_url_from_core(SERVICE_NAME)
        if not service_base_url:
            raise RuntimeError(f"無法找到服務 '{SERVICE_NAME}' 的 URL")

        async with httpx.AsyncClient(timeout=300.0) as client:
            for step in sorted(steps, key=lambda s: s.get('step_order', 0)):
                step_id = step['id']
                log.info(f"工作流 #{workflow_id}: 開始執行步驟 #{step_id} - 指令: {step['command']}")
                workflow_manager.update_step_status(workflow_id, step_id, 'running')

                try:
                    target_url = f"{service_base_url}/execute_task"
                    payload = {"command": step['command'], "parameters": step['parameters']}

                    response = await client.post(target_url, json=payload)
                    response.raise_for_status()

                    result = response.json()
                    log.info(f"步驟 #{step_id} 執行成功，結果: {result}")
                    workflow_manager.update_step_status(workflow_id, step_id, 'success', result=str(result))

                except Exception as e:
                    has_errors = True
                    error_message = f"步驟 #{step_id} ({step['command']}) 執行失敗: {str(e)}"
                    log.error(error_message, exc_info=True)
                    workflow_manager.update_step_status(workflow_id, step_id, 'failed', error=error_message)
                    continue

        final_status = 'completed_with_errors' if has_errors else 'completed'
        workflow_manager.update_workflow_status(workflow_id, final_status)
        log.info(f"工作流 #{workflow_id} 執行完畢，最終狀態: {final_status}")

    except Exception as e:
        error_message = f"工作流 #{workflow_id} 執行期間發生嚴重錯誤: {str(e)}"
        log.error(error_message, exc_info=True)
        workflow_manager.update_workflow_status(workflow_id, 'failed')

# --- API 端點 ---

@router.post("/", summary="建立一個新的工作流", status_code=201)
async def create_workflow(request_body: WorkflowCreateRequest):
    """建立一個新的工作流檔案。"""
    workflow = workflow_manager.create_workflow(name=request_body.name)
    if not workflow:
        raise HTTPException(status_code=500, detail="無法建立工作流檔案。")
    return {"workflow_id": workflow["id"]}

@router.post("/{workflow_id}/steps", summary="為工作流新增一個步驟", status_code=201)
async def add_workflow_step(workflow_id: str, request_body: WorkflowStepRequest):
    """為指定的工作流檔案新增一個步驟。"""
    step = workflow_manager.add_step(
        workflow_id=workflow_id,
        command=request_body.command,
        parameters=request_body.parameters,
        step_order=request_body.step_order
    )
    if not step:
        raise HTTPException(status_code=500, detail="無法為工作流新增步驟。")
    return {"step_id": step["id"]}

@router.get("/{workflow_id}", summary="獲取工作流的詳細資訊")
async def get_workflow_details(workflow_id: str):
    """獲取指定工作流的詳細資訊，包括其所有步驟。"""
    workflow = workflow_manager.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="找不到指定的工作流檔案。")

    # 'steps' 已經包含在從 YAML Front Matter 讀取的元資料中了
    return {"workflow": workflow, "steps": workflow.get("steps", [])}

@router.post("/{workflow_id}/execute", summary="開始執行一個工作流", status_code=202)
async def execute_workflow(workflow_id: str, background_tasks: BackgroundTasks):
    """觸發一個工作流在背景開始執行。"""
    if not workflow_manager.get_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="無法執行：找不到指定的工作流。")

    background_tasks.add_task(run_workflow_in_background, workflow_id)
    log.info(f"已將工作流 #{workflow_id} 的執行任務加入背景佇列。")
    return {"message": "工作流已成功觸發執行。"}

@router.get("/{workflow_id}/stream", summary="使用 SSE 串流工作流狀態")
async def stream_workflow_status(workflow_id: str, request: Request):
    """使用 Server-Sent Events (SSE) 持續回傳工作流的最新狀態。"""
    async def event_generator():
        last_data_hash = ""
        try:
            while True:
                if await request.is_disconnected():
                    log.info(f"客戶端已斷開對工作流 #{workflow_id} 的 SSE 連線。")
                    break

                status_data = workflow_manager.get_workflow(workflow_id)
                if not status_data:
                    yield f"data: {json.dumps({'error': '找不到工作流'})}\n\n"
                    break

                current_data_hash = hash(json.dumps(status_data, sort_keys=True))
                if current_data_hash != last_data_hash:
                    # 在這裡，我們直接回傳整個 workflow 物件，前端可以自己解析 steps
                    response_payload = {
                        "workflow_id": status_data["id"],
                        "workflow_status": status_data["status"],
                        "steps": status_data.get("steps", []) # 傳送步驟的詳細資訊
                    }
                    yield f"data: {json.dumps(response_payload)}\n\n"
                    last_data_hash = current_data_hash

                terminal_states = ['completed', 'completed_with_errors', 'failed']
                if status_data.get("status") in terminal_states:
                    log.info(f"工作流 #{workflow_id} 已達終止狀態，結束 SSE 串流。")
                    break

                await asyncio.sleep(2)
        except asyncio.CancelledError:
            log.info(f"工作流 #{workflow_id} 的 SSE 串流任務被取消。")
        except Exception as e:
            log.error(f"在為工作流 #{workflow_id} 串流狀態時發生錯誤: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': '串流時發生內部錯誤'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- 舊的端點，標記為棄用 ---
class IngestRequest(BaseModel):
    text: str

@router.post("/ingest_text", summary="[已棄用] 不再使用", deprecated=True)
async def proxy_ingest_text(request_body: IngestRequest):
    raise HTTPException(status_code=410, detail="此端點已棄用，請使用新的工作流建立流程。")