# src/api/routes/workflow.py
import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, AsyncGenerator

# V78 重構：不再有 DBClient，直接使用 get_db 注入的 database 模組
from ..dependencies import get_db
from src.core.workflow_engine import WorkflowEngine

log = logging.getLogger('api_gateway')
router = APIRouter(prefix="/api/workflows", tags=["Workflows"])

class WorkflowCreateRequest(BaseModel): name: str = Field(..., description="工作流的名稱")
class WorkflowCreateResponse(BaseModel): workflow_id: int
class StepCreateRequest(BaseModel):
    command: str = Field(..., description="要執行的指令名稱")
    parameters: Dict[str, Any] = Field({}, description="指令所需的參數")
class StepCreateResponse(BaseModel): step_id: int
class Workflow(BaseModel): id: int; name: str; status: str; created_at: str; updated_at: str
class WorkflowStep(BaseModel):
    id: int; workflow_id: int; step_order: int; command: str; parameters: Dict[str, Any]
    status: str; result: Dict[str, Any] | None = None; error_message: str | None = None
class WorkflowDetailResponse(BaseModel): workflow: Workflow; steps: List[WorkflowStep]

@router.post("/", response_model=WorkflowCreateResponse, summary="建立一個新的工作流")
async def create_new_workflow(request: WorkflowCreateRequest, db: Any = Depends(get_db)):
    try:
        workflow_id = db.create_workflow(name=request.name)
        if workflow_id is None: raise HTTPException(status_code=500, detail="無法在資料庫中建立工作流。")
        return WorkflowCreateResponse(workflow_id=workflow_id)
    except Exception as e: raise HTTPException(status_code=500, detail=f"建立工作流時發生錯誤: {e}")

@router.post("/{workflow_id}/steps", response_model=StepCreateResponse, summary="在工作流中新增一個步驟")
async def add_step_to_workflow(workflow_id: int, request: StepCreateRequest, db: Any = Depends(get_db)):
    try:
        existing_steps = db.get_workflow_steps(workflow_id)
        next_step_order = len(existing_steps) + 1
        step_id = db.add_workflow_step(workflow_id=workflow_id, step_order=next_step_order, command=request.command, parameters=request.parameters)
        if step_id is None: raise HTTPException(status_code=500, detail="無法在資料庫中新增步驟。")
        return StepCreateResponse(step_id=step_id)
    except Exception as e: raise HTTPException(status_code=500, detail=f"新增步驟時發生錯誤: {e}")

@router.get("/latest", response_model=WorkflowDetailResponse, summary="獲取最新的工作流")
async def get_latest_workflow(db: Any = Depends(get_db)):
    try:
        latest_workflow_data = db.get_latest_workflow()
        if not latest_workflow_data: raise HTTPException(status_code=404, detail="資料庫中沒有任何工作流。")
        workflow_id = latest_workflow_data['id']
        steps_data = db.get_workflow_steps(workflow_id)
        return WorkflowDetailResponse(**{"workflow": latest_workflow_data, "steps": steps_data})
    except Exception as e: raise HTTPException(status_code=500, detail=f"獲取最新工作流時發生內部錯誤: {e}")

@router.get("/{workflow_id}", response_model=WorkflowDetailResponse, summary="獲取工作流的詳細資訊")
async def get_workflow_details(workflow_id: int, db: Any = Depends(get_db)):
    try:
        workflow_data = db.get_workflow(workflow_id)
        if not workflow_data: raise HTTPException(status_code=404, detail=f"找不到 ID 為 {workflow_id} 的工作流。")
        steps_data = db.get_workflow_steps(workflow_id)
        return WorkflowDetailResponse(**{"workflow": workflow_data, "steps": steps_data})
    except Exception as e: raise HTTPException(status_code=500, detail=f"獲取工作流詳細資訊時發生錯誤: {e}")

@router.post("/{workflow_id}/execute", status_code=202, summary="執行一個工作流")
async def execute_workflow(workflow_id: int, background_tasks: BackgroundTasks, db: Any = Depends(get_db)):
    if not db.get_workflow(workflow_id): raise HTTPException(status_code=404, detail=f"找不到 ID 為 {workflow_id} 的工作流。")
    engine = WorkflowEngine(db_client=db)
    background_tasks.add_task(engine.run_workflow, workflow_id)
    return {"message": "工作流已成功接收並開始在背景執行。"}

@router.post("/{workflow_id}/reset", status_code=200, summary="重置一個已結束的工作流")
async def reset_workflow(workflow_id: int, db: Any = Depends(get_db)):
    try:
        if not db.reset_workflow(workflow_id): raise HTTPException(status_code=500, detail="重置工作流時資料庫操作失敗。")
        return {"message": f"工作流 {workflow_id} 已成功重置。"}
    except Exception as e: raise HTTPException(status_code=500, detail=f"重置工作流時發生內部伺服器錯誤: {e}")

@router.get("/", response_model=List[Workflow], summary="獲取所有工作流的歷史紀錄")
async def get_all_workflows(db: Any = Depends(get_db)):
    try:
        return sorted(db.get_all_workflows(), key=lambda w: w.get('created_at', ''), reverse=True)
    except Exception as e: raise HTTPException(status_code=500, detail="無法從資料庫讀取工作流列表。")

@router.get("/{workflow_id}/stream", summary="使用 SSE 串流傳輸工作流的即時狀態")
async def stream_workflow_status(request: Request, workflow_id: int, db: Any = Depends(get_db)):
    async def event_generator() -> AsyncGenerator[str, None]:
        last_data_json = ""
        try:
            while not await request.is_disconnected():
                workflow = db.get_workflow(workflow_id)
                if not workflow: yield f"data: {json.dumps({'error': 'Workflow not found'})}\n\n"; break
                steps = db.get_workflow_steps(workflow_id)
                detailed_statuses = []
                for step in steps:
                    source_url_id = step.get("parameters", {}).get("source_url_id")
                    if source_url_id and (item_details := db.get_url_by_id(source_url_id)):
                        detailed_statuses.append({"step_id": step["id"], "status_download": item_details.get("status_download"), "status_extraction": item_details.get("status_extraction"), "status_ocr": item_details.get("status_ocr"), "status_ai_summary": item_details.get("status_ai_summary"), "last_error": item_details.get("last_error_details")})
                current_data = {"workflow_status": workflow.get("status"), "steps": detailed_statuses}
                current_data_json = json.dumps(current_data)
                if current_data_json != last_data_json:
                    yield f"data: {current_data_json}\n\n"
                    last_data_json = current_data_json
                if workflow.get("status") in ['completed', 'completed_with_errors', 'failed']: break
                await asyncio.sleep(2)
        finally:
             log.info(f"結束 workflow {workflow_id} 的狀態串流。")
    return StreamingResponse(event_generator(), media_type="text/event-stream")
