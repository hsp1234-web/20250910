# src/api/routes/workflow.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Dict, Any

from src.db.client import DBClient
from src.core.workflow_engine import WorkflowEngine

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