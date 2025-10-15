# src/core/workflow_manager.py
import os
import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import yaml

# --- 日誌設定 ---
log = logging.getLogger(__name__)

# --- 常數設定 ---
# 將工作流資料夾的路徑定義為一個可配置的常數
WORKFLOWS_DIR = Path("data/workflows")

# --- 核心函式 ---

def _ensure_dir_exists():
    """確保工作流的根目錄存在。"""
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)

def _generate_workflow_id() -> str:
    """產生一個獨一無二且包含時間戳的工作流 ID。"""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short_uuid = str(uuid.uuid4())[:8]
    return f"wf_{timestamp}_{short_uuid}"

def _parse_markdown_file(file_path: Path) -> Dict[str, Any]:
    """
    解析一個 .md 檔案，將其分為 YAML Front Matter (元資料) 和 Markdown (步驟內容)。
    """
    if not file_path.is_file():
        return {"metadata": {}, "steps_markdown": ""}

    full_content = file_path.read_text(encoding='utf-8')

    # --- 使用正規表示式解析 Front Matter ---
    # 修正：讓結尾的 markdown 內容變為可選，以處理只有 front matter 的檔案
    import re
    match = re.match(r'^---\s*\n(.*?)\n---\s*?(?:\n(.*))?$', full_content, re.DOTALL)

    if match:
        yaml_content, markdown_content = match.groups()
        markdown_content = markdown_content or "" # 如果沒有 markdown 內容，則為空字串
        try:
            metadata = yaml.safe_load(yaml_content) or {}
        except yaml.YAMLError as e:
            log.error(f"解析檔案 {file_path} 的 YAML Front Matter 時出錯: {e}")
            metadata = {} # 如果解析失敗，回傳一個空的元資料
        return {"metadata": metadata, "steps_markdown": markdown_content.strip()}
    else:
        # 如果沒有 Front Matter，則將整個檔案視為 Markdown 內容
        return {"metadata": {}, "steps_markdown": full_content.strip()}

def _format_step_as_markdown(step_data: Dict[str, Any]) -> str:
    """將一個步驟的字典格式化為 Markdown 字串。"""
    # 使用 YAML 來傾印參數，以獲得一個格式良好且人類可讀的區塊
    parameters_yaml = yaml.dump(step_data.get('parameters', {}), allow_unicode=True, default_flow_style=False)

    # 建立 Markdown 字串
    md_parts = [
        f"### 步驟 {step_data['step_order']}: {step_data['command']}\n",
        f"- **ID**: `{step_data['id']}`",
        f"- **狀態**: {step_data.get('status', 'pending')}",
        f"- **參數**:\n```yaml\n{parameters_yaml.strip()}\n```"
    ]

    # 只有在有結果或錯誤時才加入這些欄位
    if 'result' in step_data and step_data['result']:
        md_parts.append(f"- **結果**: `{step_data['result']}`")
    if 'error' in step_data and step_data['error']:
        md_parts.append(f"- **錯誤**: `{step_data['error']}`")

    return "\n".join(md_parts) + "\n"


def create_workflow(name: str) -> Optional[Dict[str, Any]]:
    """
    建立一個新的工作流檔案。
    """
    try:
        _ensure_dir_exists()
        workflow_id = _generate_workflow_id()
        file_path = WORKFLOWS_DIR / f"{workflow_id}.md"

        metadata = {
            "id": workflow_id,
            "name": name,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "steps": [] # 我們將在元資料中也維護一個步驟列表，以便快速讀取
        }

        # 將元資料轉換為 YAML Front Matter 格式
        yaml_front_matter = yaml.dump(metadata, allow_unicode=True, default_flow_style=False)

        # 修正：確保前後都有換行符，以符合正規表示式的解析規則
        file_content = f"---\n{yaml_front_matter.strip()}\n---"

        file_path.write_text(file_content, encoding='utf-8')
        log.info(f"已成功建立新的工作流檔案: {file_path}")
        return metadata
    except Exception as e:
        log.error(f"建立工作流檔案時發生錯誤: {e}", exc_info=True)
        return None

def add_step(workflow_id: str, command: str, parameters: Dict, step_order: int) -> Optional[Dict[str, Any]]:
    """
    為指定的工作流新增一個步驟。
    """
    file_path = WORKFLOWS_DIR / f"{workflow_id}.md"
    if not file_path.is_file():
        log.error(f"找不到工作流檔案: {workflow_id}.md")
        return None

    try:
        parsed_data = _parse_markdown_file(file_path)
        metadata = parsed_data["metadata"]

        step_id = str(uuid.uuid4())
        new_step_data = {
            "id": step_id,
            "step_order": step_order,
            "command": command,
            "parameters": parameters,
            "status": "pending"
        }

        # 更新元資料中的步驟列表
        metadata.get("steps", []).append(new_step_data)

        # 格式化新的檔案內容
        new_yaml_front_matter = yaml.dump(metadata, allow_unicode=True, default_flow_style=False)
        new_step_markdown = _format_step_as_markdown(new_step_data)

        # 將新步驟附加到現有的 Markdown 內容後面
        updated_markdown_content = parsed_data.get("steps_markdown", "") + "\n" + new_step_markdown

        file_content = f"---\n{new_yaml_front_matter}---\n\n{updated_markdown_content.strip()}"

        file_path.write_text(file_content, encoding='utf-8')
        log.info(f"已為工作流 {workflow_id} 新增步驟 {step_id}")
        return new_step_data

    except Exception as e:
        log.error(f"為工作流 {workflow_id} 新增步驟時發生錯誤: {e}", exc_info=True)
        return None


def get_workflow(workflow_id: str) -> Optional[Dict[str, Any]]:
    """
    讀取並解析一個工作流檔案。
    為了效率，此函式只解析 YAML Front Matter。
    詳細的步驟內容由 get_workflow_steps 提供。
    """
    file_path = WORKFLOWS_DIR / f"{workflow_id}.md"
    if not file_path.is_file():
        return None

    try:
        parsed_data = _parse_markdown_file(file_path)
        return parsed_data.get("metadata")
    except Exception as e:
        log.error(f"讀取工作流 {workflow_id} 時發生錯誤: {e}", exc_info=True)
        return None

def get_workflow_steps(workflow_id: str) -> List[Dict[str, Any]]:
    """
    從工作流的元資料中獲取其所有步驟的摘要。
    """
    workflow_data = get_workflow(workflow_id)
    return workflow_data.get("steps", []) if workflow_data else []


def get_all_workflows() -> List[Dict[str, Any]]:
    """
    掃描目錄並回傳所有工作流的元資料列表。
    """
    _ensure_dir_exists()
    workflows = []
    for file_path in WORKFLOWS_DIR.glob("*.md"):
        try:
            workflow_data = get_workflow(file_path.stem)
            if workflow_data:
                workflows.append(workflow_data)
        except Exception as e:
            log.error(f"讀取工作流列表時，處理檔案 {file_path} 失敗: {e}")
            continue
    # 按建立時間降序排序
    return sorted(workflows, key=lambda w: w.get('created_at', ''), reverse=True)


def update_workflow_status(workflow_id: str, status: str) -> bool:
    """更新工作流的總體狀態。"""
    file_path = WORKFLOWS_DIR / f"{workflow_id}.md"
    if not file_path.is_file():
        return False

    try:
        parsed_data = _parse_markdown_file(file_path)
        metadata = parsed_data["metadata"]
        metadata['status'] = status

        new_yaml_front_matter = yaml.dump(metadata, allow_unicode=True, default_flow_style=False)
        file_content = f"---\n{new_yaml_front_matter}---\n\n{parsed_data['steps_markdown']}"
        file_path.write_text(file_content, encoding='utf-8')
        return True
    except Exception as e:
        log.error(f"更新工作流 {workflow_id} 狀態時出錯: {e}", exc_info=True)
        return False

def update_step_status(workflow_id: str, step_id: str, status: str, result: Optional[str] = None, error: Optional[str] = None) -> bool:
    """
    更新特定步驟的狀態。
    注意：這個實現比較低效，因為它重寫了整個檔案。
    在高效能場景下，需要更精細的行內替換。但在目前場景下，可讀性和可靠性優先。
    """
    file_path = WORKFLOWS_DIR / f"{workflow_id}.md"
    if not file_path.is_file():
        return False

    try:
        parsed_data = _parse_markdown_file(file_path)
        metadata = parsed_data["metadata"]

        # 尋找並更新元資料中的步驟
        step_found = False
        for step in metadata.get("steps", []):
            if step.get("id") == step_id:
                step['status'] = status
                if result is not None:
                    step['result'] = result
                if error is not None:
                    step['error'] = error
                step_found = True
                break

        if not step_found:
            log.warning(f"在工作流 {workflow_id} 中找不到步驟 ID {step_id}")
            return False

        # 重新產生整個檔案的內容
        new_yaml_front_matter = yaml.dump(metadata, allow_unicode=True, default_flow_style=False)

        # 重新產生所有步驟的 Markdown
        all_steps_markdown = "\n".join([_format_step_as_markdown(s) for s in metadata["steps"]])

        file_content = f"---\n{new_yaml_front_matter}---\n\n{all_steps_markdown.strip()}"
        file_path.write_text(file_content, encoding='utf-8')
        return True

    except Exception as e:
        log.error(f"更新步驟 {step_id} 狀態時出錯: {e}", exc_info=True)
        return False