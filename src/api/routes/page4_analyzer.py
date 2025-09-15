# --- 檔案: src/api/routes/page4_analyzer.py ---
# --- 說明: 此檔案已於 2025-09-12 重構，以支援兩階段 AI 分析流程。---
# --- 2025-09-15 更新：再次重構，將單一分析流程拆分為三個獨立的、可手動觸發的階段。

import logging
import sys
import json
import uuid
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel

# --- 路徑修正與模듈匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 核心模組匯入 ---
from db.client import get_client
from db.database import get_db_connection
from core import key_manager, prompt_manager
from tools.gemini_manager import GeminiManager
# JULES: 為了新的績效分析階段，在此處直接匯入
from tools.quantitative_analyzer import calculate_performance_stats

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()
DB_CLIENT = get_client()
TEMP_JSON_DIR = SRC_DIR.parent / "temp_json"
REPORTS_DIR = SRC_DIR.parent / "reports"

# 確保暫存和報告目錄存在
TEMP_JSON_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

import asyncio
import functools

# --- Pydantic 模型 ---
class Stage1Request(BaseModel):
    file_ids: List[int]
    model_name: str

class PerformanceAnalysisRequest(BaseModel):
    task_ids: List[int]

class Stage2Request(BaseModel):
    task_ids: List[int]
    model_name: str

# --- 重構後的背景任務函式 (同步阻塞部分) ---
def _run_stage1_blocking_task(task_id: int, file_id: int, model_name: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """
    執行第一階段 AI 分析的同步阻塞部分。
    """
    log.info(f"第一階段任務實際執行開始：task_id={task_id}, file_id={file_id}, model={model_name}")
    try:
        all_prompts = prompt_manager.get_all_prompts()
        prompt_template = all_prompts.get("stage_1_extraction_prompt")
        if not prompt_template:
            raise ValueError("在提示詞庫中找不到 'stage_1_extraction_prompt'。")

        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")
        gemini = GeminiManager(api_keys=valid_keys)

        analysis_task_data = DB_CLIENT.get_analysis_task(task_id=task_id)
        if not analysis_task_data or not analysis_task_data['file_content_for_analysis']:
            raise ValueError(f"分析任務 {task_id} 中找不到可供分析的檔案內容。")
        text_content = analysis_task_data['file_content_for_analysis']

        prompt = prompt_template.format(document_text=text_content)

        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"stage1_status": "gemini_processing"})
        notification_msg = {"type": "analysis_update", "task_id": task_id, "status": "gemini_processing", "stage": 1, "result": DB_CLIENT.get_analysis_task(task_id)}
        asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)

        structured_data, error, used_key, token_usage = gemini.prompt_for_json(prompt=prompt, model_name=model_name)

        if error:
            raise error

        # JULES (2025-09-15): 根據新計畫，移除此處的自動績效分析。
        # 現在績效分析將由一個獨立的 API 端點觸發。

        json_filename = f"stage1_{task_id}_{uuid.uuid4().hex[:8]}.json"
        json_path = TEMP_JSON_DIR / json_filename
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(structured_data, f, ensure_ascii=False, indent=2)

        DB_CLIENT.update_analysis_task(
            task_id=task_id,
            updates={
                "stage1_status": "completed",
                "stage1_json_path": str(json_path),
                "stage1_token_usage": token_usage
            }
        )
        log.info(f"第一階段任務成功：task_id={task_id}，JSON 已儲存至 {json_path}")

    except Exception as e:
        error_message = f"錯誤: {type(e).__name__}: {str(e)}"
        log.error(f"第一階段任務失敗：task_id={task_id}，{error_message}", exc_info=True)
        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"stage1_status": "failed", "stage1_error_log": error_message})

def _run_performance_analysis_blocking_task(task_id: int, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """
    執行績效分析的同步阻塞部分。
    """
    log.info(f"績效分析任務實際執行開始：task_id={task_id}")
    try:
        task_data = DB_CLIENT.get_analysis_task(task_id=task_id)
        json_path_str = task_data.get("stage1_json_path")
        if not json_path_str:
            raise ValueError(f"任務 {task_id} 缺少第一階段的 JSON 檔案路徑。")

        json_path = Path(json_path_str)
        if not json_path.exists():
            raise FileNotFoundError(f"JSON 檔案不存在於: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            structured_data = json.load(f)

        symbol = structured_data.get("symbol")
        url_record = DB_CLIENT.get_url_by_id(task_data['file_id'])
        start_date = url_record.get("message_date") if url_record else None

        if not (symbol and start_date):
            raise ValueError("缺少股票代號 (symbol) 或起始日期 (start_date)，無法執行績效分析。")

        performance_results = calculate_performance_stats(symbol, start_date)
        structured_data["quantitative_analysis"] = performance_results

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(structured_data, f, ensure_ascii=False, indent=2)

        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"performance_analysis_status": "completed"})
        log.info(f"績效分析任務成功：task_id={task_id}")

    except Exception as e:
        error_message = f"錯誤: {type(e).__name__}: {str(e)}"
        log.error(f"績效分析任務失敗：task_id={task_id}，{error_message}", exc_info=True)
        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"performance_analysis_status": "failed", "stage2_error_log": error_message})


def _run_stage2_blocking_task(task_id: int, model_name: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """
    執行第二階段 AI 分析 (報告生成) 的同步阻塞部分。
    """
    # ... (此函式內容維持不變) ...
    log.info(f"第二階段任務實際執行開始：task_id={task_id}, model={model_name}")
    try:
        task_data = DB_CLIENT.get_analysis_task(task_id=task_id)
        if not task_data or not task_data.get("stage1_json_path"):
            raise ValueError(f"找不到任務 {task_id} 或其第一階段的 JSON 產出路徑。")
        json_path = Path(task_data["stage1_json_path"])
        if not json_path.exists():
            raise FileNotFoundError(f"第一階段的 JSON 檔案不存在於路徑：{json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            structured_data = json.load(f)

        all_prompts = prompt_manager.get_all_prompts()
        prompt_template = all_prompts.get("stage_2_generation_prompt")
        if not prompt_template:
            raise ValueError("在提示詞庫中找不到 'stage_2_generation_prompt'。")
        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")
        gemini = GeminiManager(api_keys=valid_keys)

        prompt = prompt_template.format(data_package=json.dumps(structured_data, ensure_ascii=False, indent=2))

        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"stage2_status": "gemini_processing"})
        notification_msg = {"type": "analysis_update", "task_id": task_id, "status": "gemini_processing", "stage": 2, "result": DB_CLIENT.get_analysis_task(task_id)}
        asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)

        report_html, error, used_key, token_usage = gemini.prompt_for_text(prompt=prompt, model_name=model_name)

        if error:
            raise error

        report_filename = f"report_{task_id}_{uuid.uuid4().hex[:8]}.html"
        report_path = REPORTS_DIR / report_filename
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_html)

        DB_CLIENT.update_analysis_task(
            task_id=task_id,
            updates={
                "stage2_status": "completed",
                "stage2_report_path": str(report_path),
                "stage2_token_usage": token_usage
            }
        )
        log.info(f"第二階段任務成功：task_id={task_id}，報告已儲存至 {report_path}")

    except Exception as e:
        error_message = f"錯誤: {type(e).__name__}: {str(e)}"
        log.error(f"第二階段任務失敗：task_id={task_id}，{error_message}", exc_info=True)
        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"stage2_status": "failed", "stage2_error_log": error_message})


# --- 新的非同步包裝函式 (用於併發控制) ---
async def run_analysis_task_wrapper(task_id: int, semaphore: asyncio.Semaphore, blocking_func, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, **kwargs):
    """
    一個通用的非同步包裝函式，用於控制併發並執行阻塞的分析任務。
    """
    async with semaphore:
        log.info(f"任務 {task_id} 已取得信號量，準備執行...")
        stage_key_prefix = kwargs.get("stage_key_prefix", "stage1")

        DB_CLIENT.update_analysis_task(task_id=task_id, updates={
            f"{stage_key_prefix}_status": "processing",
            f"{stage_key_prefix}_model": kwargs.get("model_name")
        })

        notification_msg = {"type": "analysis_update", "task_id": task_id, "status": "processing", "stage_key": stage_key_prefix, "result": DB_CLIENT.get_analysis_task(task_id)}
        await queue.put(notification_msg)

        try:
            func_kwargs = kwargs.copy()
            func_kwargs.pop('stage_key_prefix', None)
            partial_func = functools.partial(blocking_func, task_id=task_id, queue=queue, loop=loop, **func_kwargs)
            await loop.run_in_executor(None, partial_func)
        except Exception as e:
            log.error(f"包裝函式捕獲到未預期的錯誤 (任務 {task_id}): {e}", exc_info=True)
        finally:
            log.info(f"任務 {task_id} 執行完畢，釋放信號量。")
            final_task_state = DB_CLIENT.get_analysis_task(task_id)
            final_notification_msg = {"type": "analysis_update", "task_type": f"analysis_{stage_key_prefix}", "task_id": task_id, "status": final_task_state.get(f'{stage_key_prefix}_status'), "result": final_task_state}
            await queue.put(final_notification_msg)

# --- 新的 API 端點 ---

@router.post("/start_stage1_analysis")
async def start_stage1_analysis(request: Request, payload: Stage1Request, background_tasks: BackgroundTasks):
    """啟動第一階段：JSON 提取"""
    # ... (此函式邏輯基本不變，但 stage_key_prefix 要設定) ...
    semaphore = request.app.state.analysis_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()
    tasks_created = []
    for file_id in payload.file_ids:
        task = DB_CLIENT.create_or_get_analysis_task(file_id=file_id, filename=f"file_{file_id}")
        if task:
            DB_CLIENT.update_analysis_task(task_id=task['id'], updates={"stage1_status": "pending", "stage1_error_log": None, "stage1_json_path": None, "performance_analysis_status": "pending"})
            background_tasks.add_task(run_analysis_task_wrapper, task_id=task['id'], semaphore=semaphore, blocking_func=_run_stage1_blocking_task, queue=queue, loop=loop, file_id=file_id, model_name=payload.model_name, stage_key_prefix="stage1")
            tasks_created.append(task['id'])
    return {"message": f"已成功為 {len(tasks_created)} 個檔案排入第一階段分析佇列。"}

@router.post("/start_performance_analysis")
async def start_performance_analysis(request: Request, payload: PerformanceAnalysisRequest, background_tasks: BackgroundTasks):
    """啟動績效分析"""
    semaphore = request.app.state.analysis_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()
    for task_id in payload.task_ids:
        task_data = DB_CLIENT.get_analysis_task(task_id=task_id)
        if task_data and task_data['stage1_status'] == 'completed':
            background_tasks.add_task(run_analysis_task_wrapper, task_id=task_id, semaphore=semaphore, blocking_func=_run_performance_analysis_blocking_task, queue=queue, loop=loop, stage_key_prefix="performance_analysis")
    return {"message": f"已為 {len(payload.task_ids)} 個符合條件的任務啟動績效分析。"}

@router.post("/start_stage2_analysis")
async def start_stage2_analysis(request: Request, payload: Stage2Request, background_tasks: BackgroundTasks):
    """啟動第二階段：報告生成"""
    # ... (此函式邏輯基本不變，但要檢查 performance_analysis_status) ...
    semaphore = request.app.state.analysis_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()
    for task_id in payload.task_ids:
        task_data = DB_CLIENT.get_analysis_task(task_id=task_id)
        if task_data and task_data.get('performance_analysis_status') == 'completed':
            background_tasks.add_task(run_analysis_task_wrapper, task_id=task_id, semaphore=semaphore, blocking_func=_run_stage2_blocking_task, queue=queue, loop=loop, model_name=payload.model_name, stage_key_prefix="stage2")
    return {"message": f"已為 {len(payload.task_ids)} 個符合條件的任務啟動第二階段分析。"}

# --- 新的 GET 端點，為各子頁面提供資料 ---

@router.get("/files_for_stage1")
async def get_files_for_stage1():
    """獲取所有已處理、可供進行第一階段分析的檔案列表。"""
    conn = get_db_connection()
    # 選擇那些已處理但尚未成功進入分析任務的檔案
    rows = conn.execute("""
        SELECT e.id, e.local_path
        FROM extracted_urls e
        LEFT JOIN analysis_tasks a ON e.id = a.file_id
        WHERE e.status = 'processed' AND a.id IS NULL
        ORDER BY e.created_at DESC
    """).fetchall()
    conn.close()
    return [{"id": row['id'], "filename": Path(row['local_path']).name} for row in rows]

@router.get("/files_for_performance_analysis")
async def get_files_for_performance_analysis():
    """獲取已完成第一階段、可進行績效分析的任務列表。"""
    tasks = DB_CLIENT.get_tasks_by_status(stage1_status='completed', performance_analysis_status='pending')
    return tasks

@router.get("/files_for_stage2")
async def get_files_for_stage2():
    """獲取已完成績效分析、可進行報告生成的任務列表。"""
    tasks = DB_CLIENT.get_tasks_by_status(performance_analysis_status='completed', stage2_status='pending')
    return tasks

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
