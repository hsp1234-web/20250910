# src/api/routes/workflow.py
# src/api/routes/workflow.py
import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, AsyncGenerator

from src.db.client import DBClient
from src.core.workflow_engine import WorkflowEngine

# --- 日誌設定 ---
log = logging.getLogger('api_gateway')

# --- 路由器與依賴注入 ---
router = APIRouter(
    prefix="/api/workflows",
    tags=["Workflows"],
)

def get_db_client():
    """提供一個 DBClient 的共享實例。"""
    return DBClient()

# --- 資料模型 (Pydantic Models) ---
class WorkflowCreateRequest(BaseModel):
    name: str = Field(..., description="工作流的名稱")

class WorkflowCreateResponse(BaseModel):
    workflow_id: int

class StepCreateRequest(BaseModel):
    command: str = Field(..., description="要執行的指令名稱")
    parameters: Dict[str, Any] = Field({}, description="指令所需的參數")

class StepCreateResponse(BaseModel):
    step_id: int

class Workflow(BaseModel):
    id: int
    name: str
    status: str
    created_at: str
    updated_at: str

class WorkflowStep(BaseModel):
    id: int
    workflow_id: int
    step_order: int
    command: str
    parameters: Dict[str, Any]
    status: str
    result: Dict[str, Any] | None = None
    error_message: str | None = None

class WorkflowDetailResponse(BaseModel):
    workflow: Workflow
    steps: List[WorkflowStep]


# --- API 端點 ---

@router.post("/", response_model=WorkflowCreateResponse, summary="建立一個新的工作流")
async def create_new_workflow(
    request: WorkflowCreateRequest,
    db: DBClient = Depends(get_db_client)
):
    """
    建立一個空的工作流容器，並回傳其唯一的 ID。
    """
    try:
        workflow_id = db.create_workflow(name=request.name)
        if workflow_id is None:
            raise HTTPException(status_code=500, detail="無法在資料庫中建立工作流。")
        return WorkflowCreateResponse(workflow_id=workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"建立工作流時發生錯誤: {e}")

@router.post("/{workflow_id}/steps", response_model=StepCreateResponse, summary="在工作流中新增一個步驟")
async def add_step_to_workflow(
    workflow_id: int,
    request: StepCreateRequest,
    db: DBClient = Depends(get_db_client)
):
    """
    在指定的工作流中新增一個指令步驟。
    """
    try:
        # 1. 取得目前工作流的步驟數量，以決定新步驟的順序
        existing_steps = db.get_workflow_steps(workflow_id)
        next_step_order = len(existing_steps) + 1

        # 2. 新增步驟
        step_id = db.add_workflow_step(
            workflow_id=workflow_id,
            step_order=next_step_order,
            command=request.command,
            parameters=request.parameters
        )
        if step_id is None:
            raise HTTPException(status_code=500, detail="無法在資料庫中新增步驟。")
        return StepCreateResponse(step_id=step_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"新增步驟時發生錯誤: {e}")

@router.get("/latest", response_model=WorkflowDetailResponse, summary="獲取最新的工作流")
async def get_latest_workflow(db: DBClient = Depends(get_db_client)):
    """
    (Jules @ 2025-10-15) 新增端點
    檢索最新的（即最後建立的）工作流及其詳細步驟。
    主要用於在不指定 ID 的情況下加載工作流編輯器。
    """
    try:
        latest_workflow_data = db.get_latest_workflow()
        if not latest_workflow_data:
            raise HTTPException(status_code=404, detail="資料庫中沒有任何工作流。")

        workflow_id = latest_workflow_data['id']
        steps_data = db.get_workflow_steps(workflow_id)

        response = {
            "workflow": latest_workflow_data,
            "steps": steps_data
        }
        return WorkflowDetailResponse(**response)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"獲取最新工作流時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"獲取最新工作流時發生內部錯誤: {e}")


@router.get("/{workflow_id}", response_model=WorkflowDetailResponse, summary="獲取工作流的詳細資訊")
async def get_workflow_details(
    workflow_id: int,
    db: DBClient = Depends(get_db_client)
):
    """
    獲取一個工作流的詳細資訊，包括其所有的步驟列表。
    """
    try:
        workflow_data = db.get_workflow(workflow_id)
        if not workflow_data:
            raise HTTPException(status_code=404, detail=f"找不到 ID 為 {workflow_id} 的工作流。")

        steps_data = db.get_workflow_steps(workflow_id)

        # 使用 Pydantic 模型進行資料驗證和轉換
        response = {
            "workflow": workflow_data,
            "steps": steps_data
        }
        return WorkflowDetailResponse(**response)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取工作流詳細資訊時發生錯誤: {e}")


@router.post("/{workflow_id}/execute", status_code=202, summary="執行一個工作流")
async def execute_workflow(
    workflow_id: int,
    background_tasks: BackgroundTasks,
    db: DBClient = Depends(get_db_client)
):
    """
    非同步地觸發一個工作流的執行。
    此端點會立即回傳，並在背景執行實際的工作流。
    """
    # 檢查工作流是否存在
    workflow = db.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"找不到 ID 為 {workflow_id} 的工作流。")

    # 實例化引擎並將其執行加入到背景任務
    engine = WorkflowEngine(db_client=db)
    background_tasks.add_task(engine.run_workflow, workflow_id)

    return {"message": "工作流已成功接收並開始在背景執行。"}


@router.post("/{workflow_id}/reset", status_code=200, summary="重置一個已結束的工作流")
async def reset_workflow(
    workflow_id: int,
    db: DBClient = Depends(get_db_client)
):
    """
    (Jules @ 2025-10-15) 新增端點
    將一個已完成或失敗的工作流及其所有步驟的狀態重置為 'pending'。
    這允許使用者從編輯器介面重新執行相同的工作流。
    """
    try:
        success = db.reset_workflow(workflow_id)
        if not success:
            raise HTTPException(status_code=500, detail="重置工作流時資料庫操作失敗。")
        return {"message": f"工作流 {workflow_id} 已成功重置。"}
    except Exception as e:
        log.error(f"重置工作流 {workflow_id} 時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重置工作流時發生內部伺服器錯誤: {e}")


@router.get("/", response_model=List[Workflow], summary="獲取所有工作流的歷史紀錄")
async def get_all_workflows(db: DBClient = Depends(get_db_client)):
    """
    從資料庫中檢索所有已建立的工作流，並按建立時間降序排序。
    (Jules @ 2025-10-15) 從 line_workflow_api.py 移至此處。
    """
    try:
        workflows_data = db.get_all_workflows()
        # Pydantic 會自動驗證列表中的每個項目
        return sorted(workflows_data, key=lambda w: w.get('created_at', ''), reverse=True)
    except Exception as e:
        log.error(f"獲取所有工作流時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法從資料庫讀取工作流列表。")


@router.get("/{workflow_id}/stream", summary="使用 SSE 串流傳輸工作流的即時狀態")
async def stream_workflow_status(
    request: Request,
    workflow_id: int,
    db: DBClient = Depends(get_db_client)
):
    """
    (Jules @ 2025-10-14) 新增的 SSE 端點。
    使用 Server-Sent Events 向客戶端即時推送工作流的詳細狀態更新。
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            last_data_json = ""
            while True:
                # 檢查客戶端是否已斷開連線
                if await request.is_disconnected():
                    print(f"客戶端對 workflow {workflow_id} 的連線已中斷。")
                    break

                # 從資料庫獲取工作流和步驟的最新狀態
                workflow = db.get_workflow(workflow_id)
                if not workflow:
                    # 如果工作流不存在，發送一個錯誤事件並關閉串流
                    error_data = {"error": "Workflow not found"}
                    yield f"data: {json.dumps(error_data)}\n\n"
                    break

                steps = db.get_workflow_steps(workflow_id)

                # 從 `line_workflow_api.py` 借用並調整獲取詳細狀態的邏輯
                detailed_statuses = []
                for step in steps:
                    source_url_id = step.get("parameters", {}).get("source_url_id")
                    if not source_url_id:
                        continue
                    item_details = db.get_url_by_id(source_url_id)
                    if not item_details:
                        continue
                    detailed_statuses.append({
                        "step_id": step["id"],
                        "status_download": item_details.get("status_download"),
                        "status_extraction": item_details.get("status_extraction"),
                        "status_ocr": item_details.get("status_ocr"),
                        "status_ai_summary": item_details.get("status_ai_summary"),
                        "last_error": item_details.get("last_error_details")
                    })

                # 組合完整的狀態 payload
                current_data = {
                    "workflow_status": workflow.get("status"),
                    "steps": detailed_statuses
                }

                current_data_json = json.dumps(current_data)

                # 只有在資料有變動時才發送更新，以節省頻寬
                if current_data_json != last_data_json:
                    yield f"data: {current_data_json}\n\n"
                    last_data_json = current_data_json

                # 如果工作流達到終止狀態，則發送最後一次更新後退出迴圈
                terminal_states = ['completed', 'completed_with_errors', 'failed']
                if workflow.get("status") in terminal_states:
                    break

                # 等待一段時間再進行下一次檢查
                await asyncio.sleep(2)

        except asyncio.CancelledError:
            # 當客戶端斷開連線時，FastAPI 會觸發此異常
            print(f"對 workflow {workflow_id} 的串流任務被取消。")
        finally:
             print(f"結束 workflow {workflow_id} 的狀態串流。")

    return StreamingResponse(event_generator(), media_type="text/event-stream")