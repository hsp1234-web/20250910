# --- 檔案: src/api/routes/page4_analyzer.py ---
# --- 說明: 此檔案已於 2025-09-12 重構，以支援兩階段 AI 分析流程。---

import logging
import sys
import json
import uuid
import requests
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from pydantic import BaseModel

# --- 路徑修正與模듈匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 核心模組匯入 ---
from db.client import get_client
from db.database import get_db_connection
from core import key_manager, prompt_manager
from tools.gemini_manager import GeminiManager

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()
DB_CLIENT = get_client()
TEMP_JSON_DIR = SRC_DIR.parent / "temp_json"
REPORTS_DIR = SRC_DIR.parent / "reports"

# 確保暫存和報告目錄存在
TEMP_JSON_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# --- Pydantic 模型 ---
class Stage1Request(BaseModel):
    file_ids: List[int]
    model_name: str

class Stage2Request(BaseModel):
    task_ids: List[int]
    model_name: str

# --- WebSocket 通知輔助函式 ---
def _send_websocket_notification(server_port: int, message: Dict):
    """向主伺服器的內部端點發送通知。"""
    try:
        url = f"http://127.0.0.1:{server_port}/api/internal/notify_analysis_update"
        response = requests.post(url, json=message, timeout=5)
        response.raise_for_status()
    except requests.RequestException as e:
        log.error(f"無法發送 WebSocket 通知: {e}")

# --- 新的背景任務函式 (第一階段) ---
def run_stage1_task(task_id: int, file_id: int, model_name: str, server_port: int):
    """
    執行第一階段 AI 分析：從檔案內容提取結構化 JSON。
    """
    log.info(f"第一階段背景任務啟動：task_id={task_id}, file_id={file_id}, model={model_name}")

    try:
        # 1. 更新任務狀態為「處理中」
        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"stage1_status": "processing", "stage1_model": model_name})
        _send_websocket_notification(server_port, {"type": "STATUS_UPDATE"})

        # 2. 初始化 Gemini Manager
        all_prompts = prompt_manager.get_all_prompts()
        prompt_template = all_prompts.get("stage_1_extraction_prompt")
        if not prompt_template:
            raise ValueError("在提示詞庫中找不到 'stage_1_extraction_prompt'。")

        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")
        gemini = GeminiManager(api_keys=valid_keys)

        # 3. 從資料庫獲取檔案內容 (*** 核心邏輯修改 ***)
        # 新邏輯：直接從 analysis_tasks 表讀取已儲存的檔案內容
        analysis_task_data = DB_CLIENT.get_analysis_task(task_id=task_id)
        if not analysis_task_data or not analysis_task_data.get('file_content_for_analysis'):
            raise ValueError(f"分析任務 {task_id} 中找不到可供分析的檔案內容 (file_content_for_analysis)。")

        text_content = analysis_task_data['file_content_for_analysis']

        # 4. 執行 AI 資料提取
        prompt = prompt_template.format(document_text=text_content)
        structured_data = gemini.prompt_for_json(prompt=prompt, model_name=model_name)
        if not structured_data:
            raise RuntimeError("AI 資料提取失敗，模型回傳內容為空。")

        # 5. 儲存 JSON 結果到檔案
        json_filename = f"stage1_{task_id}_{uuid.uuid4().hex[:8]}.json"
        json_path = TEMP_JSON_DIR / json_filename
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(structured_data, f, ensure_ascii=False, indent=2)

        # 6. 更新任務狀態為「完成」
        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"stage1_status": "completed", "stage1_json_path": str(json_path)})
        log.info(f"第一階段任務成功：task_id={task_id}，JSON 已儲存至 {json_path}")

    except Exception as e:
        error_message = f"錯誤: {type(e).__name__}: {str(e)}"
        log.error(f"第一階段任務失敗：task_id={task_id}，{error_message}", exc_info=True)
        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"stage1_status": "failed", "stage1_error_log": error_message})

    finally:
        _send_websocket_notification(server_port, {"type": "STATUS_UPDATE"})


# --- 新的背景任務函式 (第二階段) ---
def run_stage2_task(task_id: int, model_name: str, server_port: int):
    """
    執行第二階段 AI 分析：根據 JSON 生成分析報告。
    """
    log.info(f"第二階段背景任務啟動：task_id={task_id}, model={model_name}")

    try:
        # 1. 更新任務狀態為「處理中」
        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"stage2_status": "processing", "stage2_model_used": model_name})
        _send_websocket_notification(server_port, {"type": "STATUS_UPDATE"})

        # 2. 獲取第一階段產生的 JSON 路徑
        task_data = DB_CLIENT.get_analysis_task(task_id=task_id)
        if not task_data or not task_data.get("stage1_json_path"):
            raise ValueError(f"找不到任務 {task_id} 或其第一階段的 JSON 產出路徑。")

        json_path = Path(task_data["stage1_json_path"])
        if not json_path.exists():
            raise FileNotFoundError(f"第一階段的 JSON 檔案不存在於路徑：{json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            structured_data = json.load(f)

        # 3. 初始化 Gemini Manager
        all_prompts = prompt_manager.get_all_prompts()
        prompt_template = all_prompts.get("stage_2_generation_prompt")
        if not prompt_template:
            raise ValueError("在提示詞庫中找不到 'stage_2_generation_prompt'。")

        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")
        gemini = GeminiManager(api_keys=valid_keys)

        # 4. 執行 AI 報告生成
        prompt = prompt_template.format(data_package=json.dumps(structured_data, ensure_ascii=False, indent=2))
        report_html = gemini.prompt_for_text(prompt=prompt, model_name=model_name)
        if not report_html:
            raise RuntimeError("AI 報告生成失敗，模型回傳內容為空。")

        # 5. 儲存報告
        report_filename = f"report_{task_id}_{uuid.uuid4().hex[:8]}.html"
        report_path = REPORTS_DIR / report_filename
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_html)

        # 6. 更新任務狀態為「完成」
        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"stage2_status": "completed", "stage2_report_path": str(report_path)})
        log.info(f"第二階段任務成功：task_id={task_id}，報告已儲存至 {report_path}")

    except Exception as e:
        error_message = f"錯誤: {type(e).__name__}: {str(e)}"
        log.error(f"第二階段任務失敗：task_id={task_id}，{error_message}", exc_info=True)
        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"stage2_status": "failed", "stage2_error_log": error_message})

    finally:
        _send_websocket_notification(server_port, {"type": "STATUS_UPDATE"})


# --- 新的 API 端點 ---

@router.post("/start_stage1_analysis")
async def start_stage1_analysis(request: Request, payload: Stage1Request, background_tasks: BackgroundTasks):
    """啟動第一階段：JSON 提取"""
    if not payload.file_ids:
        raise HTTPException(status_code=400, detail="檔案 ID 列表不可為空。")

    server_port = request.app.state.server_port
    if not server_port:
        raise HTTPException(status_code=500, detail="無法確定伺服器埠號。")

    tasks_created = []
    # 暫時直接連線獲取檔名，理想情況應透過 client
    conn = get_db_connection()
    cursor = conn.cursor()
    for file_id in payload.file_ids:
        cursor.execute("SELECT local_path FROM extracted_urls WHERE id = ?", (file_id,))
        file_data = cursor.fetchone()
        filename = Path(file_data['local_path']).name if file_data else f"未知檔案_{file_id}"

        # 為每個檔案建立或取得分析任務記錄
        task = DB_CLIENT.create_or_get_analysis_task(file_id=file_id, filename=filename)
        if task:
            # 如果任務已存在且成功過，可以選擇重置或跳過，此處選擇重置
            DB_CLIENT.update_analysis_task(task_id=task['id'], updates={
                "stage1_status": "pending", "stage1_error_log": None, "stage1_json_path": None,
                "stage2_status": "pending", "stage2_error_log": None, "stage2_report_path": None
            })
            background_tasks.add_task(run_stage1_task, task['id'], file_id, payload.model_name, server_port)
            tasks_created.append(task['id'])
    conn.close()

    return {"message": f"已成功為 {len(tasks_created)} 個檔案啟動第一階段分析任務。"}

@router.post("/start_stage2_analysis")
async def start_stage2_analysis(request: Request, payload: Stage2Request, background_tasks: BackgroundTasks):
    """啟動第二階段：報告生成"""
    if not payload.task_ids:
        raise HTTPException(status_code=400, detail="任務 ID 列表不可為空。")

    server_port = request.app.state.server_port
    if not server_port:
        raise HTTPException(status_code=500, detail="無法確定伺服器埠號。")

    for task_id in payload.task_ids:
        task_data = DB_CLIENT.get_analysis_task(task_id=task_id)
        if task_data and task_data['stage1_status'] == 'completed':
            background_tasks.add_task(run_stage2_task, task_id, payload.model_name, server_port)
        else:
            log.warning(f"跳過任務 ID {task_id} 的第二階段分析，因為其第一階段未完成。")

    return {"message": f"已為 {len(payload.task_ids)} 個符合條件的任務啟動第二階段分析。"}

@router.get("/analysis_status")
async def get_analysis_status():
    """獲取所有分析任務的最新狀態"""
    tasks = DB_CLIENT.get_all_analysis_tasks()
    return tasks

@router.get("/stage1_result/{task_id}")
async def get_stage1_result(task_id: int):
    """獲取指定任務第一階段產出的 JSON 內容"""
    task = DB_CLIENT.get_analysis_task(task_id=task_id)
    if not task or not task.get("stage1_json_path"):
        raise HTTPException(status_code=404, detail="找不到任務或其第一階段的 JSON 產出。")

    json_path = Path(task["stage1_json_path"])
    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"JSON 檔案遺失於路徑：{json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

# --- 保留但可選用的端點 ---

@router.get("/processed_files")
async def get_processed_files():
    """獲取所有已處理、可供分析的檔案列表。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, local_path FROM extracted_urls WHERE status = 'processed' OR status = 'analyzed'")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": row['id'], "filename": Path(row['local_path']).name} for row in rows if row['local_path']]

# --- 已棄用的舊版分析流程 ---

# @router.post("/start_analysis")
# async def start_analysis(request: Request, payload: AnalysisRequest, background_tasks: BackgroundTasks):
#     """(已棄用) 接收多個檔案 ID 和一個模型名稱，為其建立背景分析任務。"""
#     # ... 舊的實作 ...
#     pass

# def run_ai_analysis_task(file_ids: List[int], server_port: int, model_name: str):
#     """(已棄用) 對多個檔案執行新的兩階段 AI 分析流程。"""
#     # ... 舊的實作 ...
#     pass
