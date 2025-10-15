import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException, BackgroundTasks

# 直接匯入我們要測試的函式
from src.api.routes.line_workflow_api import (
    create_workflow,
    add_workflow_step,
    get_workflow_details,
    execute_workflow,
    WorkflowCreateRequest,
    WorkflowStepRequest
)

@pytest.mark.asyncio
@patch("src.api.routes.line_workflow_api.workflow_manager")
async def test_create_workflow_success(mock_wm: MagicMock):
    """直接測試 create_workflow 函式的成功路徑。"""
    mock_wm.create_workflow.return_value = {"id": "wf_test_123"}
    request = WorkflowCreateRequest(name="一個成功的測試")

    response = await create_workflow(request)

    assert response == {"workflow_id": "wf_test_123"}
    mock_wm.create_workflow.assert_called_once_with(name="一個成功的測試")

@pytest.mark.asyncio
@patch("src.api.routes.line_workflow_api.workflow_manager")
async def test_create_workflow_fails(mock_wm: MagicMock):
    """測試當 workflow_manager 回傳 None 時，create_workflow 是否引發 HTTPException。"""
    mock_wm.create_workflow.return_value = None
    request = WorkflowCreateRequest(name="一個失敗的測試")

    with pytest.raises(HTTPException) as excinfo:
        await create_workflow(request)

    assert excinfo.value.status_code == 500
    assert "無法建立工作流檔案" in excinfo.value.detail

@pytest.mark.asyncio
@patch("src.api.routes.line_workflow_api.workflow_manager")
async def test_add_step_success(mock_wm: MagicMock):
    """測試 add_workflow_step 的成功路徑。"""
    step_data = {"id": "step_abc"}
    mock_wm.add_step.return_value = step_data
    request = WorkflowStepRequest(command="TEST_CMD", parameters={"p1": "v1"}, step_order=1)

    response = await add_workflow_step("wf_123", request)

    assert response == {"step_id": "step_abc"}
    mock_wm.add_step.assert_called_once_with(
        workflow_id="wf_123",
        command="TEST_CMD",
        parameters={"p1": "v1"},
        step_order=1
    )

@pytest.mark.asyncio
@patch("src.api.routes.line_workflow_api.workflow_manager")
async def test_get_details_found(mock_wm: MagicMock):
    """直接測試 get_workflow_details 函式的成功路徑。"""
    mock_wm.get_workflow.return_value = {
        "id": "wf_abc", "name": "一個存在的工作流", "steps": [{"id": "step1"}]
    }

    response = await get_workflow_details(workflow_id="wf_abc")

    assert response["workflow"]["id"] == "wf_abc"
    assert len(response["steps"]) == 1
    mock_wm.get_workflow.assert_called_once_with("wf_abc")

@pytest.mark.asyncio
@patch("src.api.routes.line_workflow_api.workflow_manager")
async def test_get_details_not_found(mock_wm: MagicMock):
    """測試當工作流不存在時，get_workflow_details 是否引發 HTTPException。"""
    mock_wm.get_workflow.return_value = None

    with pytest.raises(HTTPException) as excinfo:
        await get_workflow_details(workflow_id="wf_nonexistent")

    assert excinfo.value.status_code == 404
    mock_wm.get_workflow.assert_called_once_with("wf_nonexistent")

@pytest.mark.asyncio
@patch("src.api.routes.line_workflow_api.run_workflow_in_background")
@patch("src.api.routes.line_workflow_api.workflow_manager")
async def test_execute_workflow_logic(mock_wm: MagicMock, mock_run_bg: MagicMock):
    """直接測試 execute_workflow 函式的邏輯。"""
    workflow_id = "wf_to_execute"
    mock_wm.get_workflow.return_value = {"id": workflow_id}

    mock_background_tasks = MagicMock(spec=BackgroundTasks)

    response = await execute_workflow(workflow_id, mock_background_tasks)

    assert response["message"] == "工作流已成功觸發執行。"
    mock_wm.get_workflow.assert_called_once_with(workflow_id)
    mock_background_tasks.add_task.assert_called_once_with(mock_run_bg, workflow_id)