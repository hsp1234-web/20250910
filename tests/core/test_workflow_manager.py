import pytest
from pathlib import Path
import yaml
import os

# 匯入我們要測試的模組
from src.core import workflow_manager

@pytest.fixture
def temp_workflows_dir(tmp_path):
    """
    一個 Pytest fixture，它會建立一個臨時的工作流目錄，
    並在測試期間將 `workflow_manager` 的 WORKFLOWS_DIR 常數指向這個臨時目錄。
    測試結束後，會自動清理這個臨時目錄。
    """
    # 建立一個臨時的 data/workflows 子目錄
    test_dir = tmp_path / "data" / "workflows"
    test_dir.mkdir(parents=True, exist_ok=True)

    # 使用 monkeypatch 來動態地修改模組常數
    original_dir = workflow_manager.WORKFLOWS_DIR
    workflow_manager.WORKFLOWS_DIR = test_dir

    yield test_dir # 將臨時目錄的路徑提供給測試函式

    # 測試結束後，恢復原始的常數值
    workflow_manager.WORKFLOWS_DIR = original_dir


def test_create_workflow(temp_workflows_dir: Path):
    """測試 `create_workflow` 函式是否能成功建立一個格式正確的 .md 檔案。"""
    workflow = workflow_manager.create_workflow(name="我的第一個檔案工作流")

    assert workflow is not None
    assert "id" in workflow
    workflow_id = workflow["id"]

    # 檢查檔案是否存在
    workflow_file = temp_workflows_dir / f"{workflow_id}.md"
    assert workflow_file.is_file()

    # 檢查檔案內容
    content = workflow_file.read_text(encoding='utf-8')
    assert content.startswith("---")
    assert content.endswith("---")

    # 解析 YAML Front Matter 並驗證
    parsed_data = workflow_manager._parse_markdown_file(workflow_file)
    metadata = parsed_data["metadata"]

    assert metadata["id"] == workflow_id
    assert metadata["name"] == "我的第一個檔案工作流"
    assert metadata["status"] == "pending"
    assert "created_at" in metadata
    assert metadata["steps"] == []

def test_add_step(temp_workflows_dir: Path):
    """測試 `add_step` 是否能成功地將一個步驟附加到現有的工作流檔案中。"""
    # 準備：先建立一個工作流
    workflow = workflow_manager.create_workflow(name="新增步驟測試")
    workflow_id = workflow["id"]

    # 行動：新增一個步驟
    step_params = {"url": "http://example.com", "source_url_id": 123}
    added_step = workflow_manager.add_step(
        workflow_id=workflow_id,
        command="PROCESS_URL",
        parameters=step_params,
        step_order=1
    )

    assert added_step is not None
    assert added_step["command"] == "PROCESS_URL"
    assert added_step["step_order"] == 1

    # 驗證：讀取檔案並檢查內容
    workflow_file = temp_workflows_dir / f"{workflow_id}.md"
    parsed_data = workflow_manager._parse_markdown_file(workflow_file)
    metadata = parsed_data["metadata"]
    markdown_content = parsed_data["steps_markdown"]

    # 驗證元資料
    assert len(metadata["steps"]) == 1
    assert metadata["steps"][0]["id"] == added_step["id"]
    assert metadata["steps"][0]["parameters"] == step_params

    # 驗證 Markdown 內容
    assert f"### 步驟 1: PROCESS_URL" in markdown_content
    assert f"- **ID**: `{added_step['id']}`" in markdown_content
    assert "url: http://example.com" in markdown_content

def test_get_all_workflows(temp_workflows_dir: Path):
    """測試 `get_all_workflows` 是否能正確地列出所有工作流。"""
    # 準備：建立兩個工作流
    workflow1 = workflow_manager.create_workflow(name="工作流一")
    workflow2 = workflow_manager.create_workflow(name="工作流二")

    # 行動：獲取所有工作流
    all_workflows = workflow_manager.get_all_workflows()

    # 斷言
    assert len(all_workflows) == 2
    # 預設是按時間降序排序，所以 wf2 應該在前面
    assert all_workflows[0]["name"] == "工作流二"
    assert all_workflows[1]["name"] == "工作流一"

def test_update_workflow_and_step_status(temp_workflows_dir: Path):
    """測試更新工作流和步驟狀態的功能。"""
    # 準備
    workflow = workflow_manager.create_workflow(name="狀態更新測試")
    workflow_id = workflow["id"]
    step = workflow_manager.add_step(workflow_id, "CMD", {}, 1)
    step_id = step["id"]

    # 行動 1: 更新步驟狀態
    success_step = workflow_manager.update_step_status(workflow_id, step_id, "success", result="成功了")
    assert success_step is True

    # 驗證 1
    updated_workflow = workflow_manager.get_workflow(workflow_id)
    assert updated_workflow["steps"][0]["status"] == "success"
    assert updated_workflow["steps"][0]["result"] == "成功了"

    # 行動 2: 更新工作流總體狀態
    success_workflow = workflow_manager.update_workflow_status(workflow_id, "completed")
    assert success_workflow is True

    # 驗證 2
    final_workflow = workflow_manager.get_workflow(workflow_id)
    assert final_workflow["status"] == "completed"