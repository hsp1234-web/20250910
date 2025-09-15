# --- 檔案: src/api/routes/page4_analyzer.py ---
# --- 說明: 此檔案已於 2025-09-12 重構，以支援兩階段 AI 分析流程。---

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

# --- WebSocket 通知輔助函式 (已由佇列取代) ---
# JULES (2025-09-13): 移除了舊的 _send_websocket_notification 函式。
# 現在所有通知都將透過一個從主應用程式傳入的 asyncio.Queue 來發送。

# --- 重構後的背景任務函式 (同步阻塞部分) ---
def _run_stage1_blocking_task(task_id: int, file_id: int, model_name: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """
    執行第一階段 AI 分析的同步阻塞部分。
    現在透過 queue 和 loop 來發送非同步通知。
    【修改】: 已移除自動執行的量化分析。
    """
    log.info(f"第一階段任務實際執行開始：task_id={task_id}, file_id={file_id}, model={model_name}")
    try:
        # 1. 初始化 Gemini Manager
        all_prompts = prompt_manager.get_all_prompts()
        prompt_template = all_prompts.get("stage_1_extraction_prompt")
        if not prompt_template:
            raise ValueError("在提示詞庫中找不到 'stage_1_extraction_prompt'。")

        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")
        gemini = GeminiManager(api_keys=valid_keys)

        # 2. 從資料庫獲取檔案內容
        analysis_task_data = DB_CLIENT.get_analysis_task(task_id=task_id)
        if not analysis_task_data or not analysis_task_data['file_content_for_analysis']:
            raise ValueError(f"分析任務 {task_id} 中找不到可供分析的檔案內容 (file_content_for_analysis)。")
        text_content = analysis_task_data['file_content_for_analysis']

        # 3. 執行 AI 資料提取
        prompt = prompt_template.format(document_text=text_content)

        # 新增：在呼叫 API 前發送一個更細緻的狀態更新
        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"stage1_status": "gemini_processing"})
        notification_msg = {"type": "analysis_update", "task_id": task_id, "status": "gemini_processing", "stage": 1, "result": DB_CLIENT.get_analysis_task(task_id)}
        asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)

        structured_data, error, used_key, token_usage = gemini.prompt_for_json(prompt=prompt, model_name=model_name)

        if error:
            raise error

        # 4. 儲存 JSON 結果到檔案
        json_filename = f"stage1_{task_id}_{uuid.uuid4().hex[:8]}.json"
        json_path = TEMP_JSON_DIR / json_filename
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(structured_data, f, ensure_ascii=False, indent=2)

        # 5. 更新任務狀態為「完成」，並記錄 token 使用量
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
    【新增】執行績效分析的同步阻塞部分。
    """
    log.info(f"績效分析任務實際執行開始：task_id={task_id}")
    try:
        from tools.quantitative_analyzer import calculate_performance_stats

        # 1. 獲取第一階段的 JSON
        task_data = DB_CLIENT.get_analysis_task(task_id=task_id)
        if not task_data or not task_data.get("stage1_json_path"):
            raise ValueError(f"找不到任務 {task_id} 或其第一階段的 JSON 產出路徑。")

        json_path = Path(task_data["stage1_json_path"])
        if not json_path.exists():
            raise FileNotFoundError(f"第一階段的 JSON 檔案不存在於路徑：{json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            stage1_data = json.load(f)

        # 2. 執行量化分析
        symbol = stage1_data.get("symbol")
        url_record = DB_CLIENT.get_url_by_id(task_data['source_document_id'])
        start_date = url_record.get("message_date") if url_record else None

        if not (symbol and start_date):
            raise ValueError(f"任務 {task_id}: 缺少 symbol 或 start_date，無法執行量化分析。")

        log.info(f"任務 {task_id}: 正在為代號 {symbol} (起始日: {start_date}) 執行量化分析...")
        performance_results = calculate_performance_stats(symbol, start_date)
        stage1_data["quantitative_analysis"] = performance_results

        # 3. 將包含績效分析的結果寫回同一個 JSON 檔案
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(stage1_data, f, ensure_ascii=False, indent=2)

        # 4. 更新資料庫狀態 (可選，這裡我們用 JSON 內容作為狀態)
        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"performance_status": "completed"}) # 假設我們新增一個欄位
        log.info(f"績效分析任務成功：task_id={task_id}")

    except Exception as e:
        error_message = f"錯誤: {type(e).__name__}: {str(e)}"
        log.error(f"績效分析任務失敗：task_id={task_id}，{error_message}", exc_info=True)
        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"performance_status": "failed", "performance_error_log": error_message})


def _run_stage2_blocking_task(task_id: int, model_name: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    """
    執行第二階段 AI 分析的同步阻塞部分。
    現在透過 queue 和 loop 來發送非同步通知。
    """
    log.info(f"第二階段任務實際執行開始：task_id={task_id}, model={model_name}")
    try:
        # 1. 獲取第一階段產生的 JSON 路徑
        task_data = DB_CLIENT.get_analysis_task(task_id=task_id)
        if not task_data or not task_data.get("stage1_json_path"):
            raise ValueError(f"找不到任務 {task_id} 或其第一階段的 JSON 產出路徑。")
        json_path = Path(task_data["stage1_json_path"])
        if not json_path.exists():
            raise FileNotFoundError(f"第一階段的 JSON 檔案不存在於路徑：{json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            structured_data = json.load(f)

        # 2. 初始化 Gemini Manager
        all_prompts = prompt_manager.get_all_prompts()
        prompt_template = all_prompts.get("stage_2_generation_prompt")
        if not prompt_template:
            raise ValueError("在提示詞庫中找不到 'stage_2_generation_prompt'。")
        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")
        gemini = GeminiManager(api_keys=valid_keys)

        # 3. 執行 AI 報告生成
        prompt = prompt_template.format(data_package=json.dumps(structured_data, ensure_ascii=False, indent=2))

        # 新增：在呼叫 API 前發送一個更細緻的狀態更新
        DB_CLIENT.update_analysis_task(task_id=task_id, updates={"stage2_status": "gemini_processing"})
        # JULES (2025-09-13): 改用佇列發送通知
        notification_msg = {"type": "analysis_update", "task_id": task_id, "status": "gemini_processing", "stage": 2, "result": DB_CLIENT.get_analysis_task(task_id)}
        asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)


        # 同樣，確保能接收到完整的元組，包含 token 使用量
        report_html, error, used_key, token_usage = gemini.prompt_for_text(prompt=prompt, model_name=model_name)

        # 同樣，檢查並直接 raise 例外物件
        if error:
            raise error

        # 4. 儲存報告
        report_filename = f"report_{task_id}_{uuid.uuid4().hex[:8]}.html"
        report_path = REPORTS_DIR / report_filename
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_html)

        # 5. 更新任務狀態為「完成」，並記錄 token 使用量
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
    現在接收 queue 和 loop 以便將通知功能傳遞下去。
    """
    async with semaphore:
        log.info(f"任務 {task_id} 已取得信號量，準備執行...")

        # 根據 kwargs 決定更新哪個狀態欄位
        stage = kwargs.get("stage")
        status_field = "status" # 預設
        if stage == "performance":
            status_field = "performance_status"
            update_payload = {status_field: "processing"}
        elif stage in [1, 2]:
            status_field = f"stage{stage}_status"
            update_payload = {status_field: "processing", f"stage{stage}_model": kwargs.get("model_name")}
        else: # for performance analysis
             update_payload = {"performance_status": "processing"}

        DB_CLIENT.update_analysis_task(task_id=task_id, updates=update_payload)

        notification_msg = {"type": "analysis_update", "task_id": task_id, "status": "processing", "stage": stage, "result": DB_CLIENT.get_analysis_task(task_id)}
        await queue.put(notification_msg)

        try:
            func_kwargs = kwargs.copy()
            func_kwargs.pop('stage', None)

            partial_func = functools.partial(blocking_func, task_id=task_id, queue=queue, loop=loop, **func_kwargs)
            await loop.run_in_executor(None, partial_func)
        except Exception as e:
            log.error(f"包裝函式捕獲到未預期的錯誤 (任務 {task_id}): {e}", exc_info=True)
        finally:
            log.info(f"任務 {task_id} 執行完畢，釋放信號量。")
            final_task_state = DB_CLIENT.get_analysis_task(task_id)
            final_status = final_task_state.get(status_field, 'unknown')
            final_notification_msg = {"type": "analysis_update", "task_type": f"analysis_stage_{stage}", "task_id": task_id, "status": final_status, "result": final_task_state}
            await queue.put(final_notification_msg)

# --- 新的 API 端點 ---

@router.post("/start_stage1_analysis")
async def start_stage1_analysis(request: Request, payload: Stage1Request, background_tasks: BackgroundTasks):
    """啟動第一階段：JSON 提取"""
    if not payload.file_ids:
        raise HTTPException(status_code=400, detail="檔案 ID 列表不可為空。")

    semaphore = request.app.state.analysis_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()

    if not semaphore or not queue:
        raise HTTPException(status_code=500, detail="伺服器狀態未完全初始化（缺少佇列或信號量）。")

    tasks_created = []
    conn = get_db_connection()
    cursor = conn.cursor()
    for file_id in payload.file_ids:
        cursor.execute("SELECT local_path FROM extracted_urls WHERE id = ?", (file_id,))
        file_data = cursor.fetchone()
        filename = Path(file_data['local_path']).name if file_data else f"未知檔案_{file_id}"

        task = DB_CLIENT.create_or_get_analysis_task(file_id=file_id, filename=filename)
        if task:
            DB_CLIENT.update_analysis_task(task_id=task['id'], updates={
                "stage1_status": "pending", "stage1_error_log": None, "stage1_json_path": None,
                "performance_status": "pending", "performance_error_log": None,
                "stage2_status": "pending", "stage2_error_log": None, "stage2_report_path": None
            })
            background_tasks.add_task(
                run_analysis_task_wrapper,
                task_id=task['id'],
                semaphore=semaphore,
                blocking_func=_run_stage1_blocking_task,
                queue=queue,
                loop=loop,
                file_id=file_id,
                model_name=payload.model_name,
                stage=1
            )
            tasks_created.append(task['id'])
    conn.close()

    return {"message": f"已成功為 {len(tasks_created)} 個檔案排入第一階段分析佇列。"}

@router.post("/start_performance_analysis")
async def start_performance_analysis(request: Request, payload: PerformanceAnalysisRequest, background_tasks: BackgroundTasks):
    """【新增】啟動績效分析"""
    if not payload.task_ids:
        raise HTTPException(status_code=400, detail="任務 ID 列表不可為空。")

    semaphore = request.app.state.analysis_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()

    for task_id in payload.task_ids:
        background_tasks.add_task(
            run_analysis_task_wrapper,
            task_id=task_id,
            semaphore=semaphore,
            blocking_func=_run_performance_analysis_blocking_task,
            queue=queue,
            loop=loop,
            stage="performance"
        )

    return {"message": f"已成功為 {len(payload.task_ids)} 個任務排入績效分析佇列。"}

@router.post("/start_stage2_analysis")
async def start_stage2_analysis(request: Request, payload: Stage2Request, background_tasks: BackgroundTasks):
    """啟動第二階段：報告生成"""
    if not payload.task_ids:
        raise HTTPException(status_code=400, detail="任務 ID 列表不可為空。")

    semaphore = request.app.state.analysis_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()

    if not semaphore or not queue:
        raise HTTPException(status_code=500, detail="伺服器狀態未完全初始化（缺少佇列或信號量）。")

    for task_id in payload.task_ids:
        task_data = DB_CLIENT.get_analysis_task(task_id=task_id)
        if task_data and task_data.get('performance_status') == 'completed':
            background_tasks.add_task(
                run_analysis_task_wrapper,
                task_id=task_id,
                semaphore=semaphore,
                blocking_func=_run_stage2_blocking_task,
                queue=queue,
                loop=loop,
                model_name=payload.model_name,
                stage=2
            )
        else:
            log.warning(f"跳過任務 ID {task_id} 的第二階段分析，因為其績效分析未完成。")

    return {"message": f"已為 {len(payload.task_ids)} 個符合條件的任務啟動第二階段分析。"}

@router.get("/files_for_stage1")
async def get_files_for_stage1():
    """【新增】獲取所有已處理、可供第一階段分析的檔案列表。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, local_path, status FROM extracted_urls WHERE status = 'processed' ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": row['id'], "filename": Path(row['local_path']).name} for row in rows if row['local_path']]

@router.get("/files_for_performance_analysis")
async def get_files_for_performance_analysis():
    """【新增】獲取已完成第一階段分析，但尚未進行績效分析的任務列表。"""
    tasks = DB_CLIENT.get_all_analysis_tasks()
    # 篩選條件：第一階段已完成，且績效分析狀態不是 'completed'
    return [t for t in tasks if t.get('stage1_status') == 'completed' and t.get('performance_status') != 'completed']

@router.get("/files_for_stage2")
async def get_files_for_stage2():
    """【新增】獲取已完成績效分析，可供生成報告的任務列表。"""
    tasks = DB_CLIENT.get_all_analysis_tasks()
    # 篩選條件：績效分析狀態為 'completed'
    return [t for t in tasks if t.get('performance_status') == 'completed']


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

# --- 已棄用的舊版分析流程 ---
# 移除了 /analysis_status 和 /processed_files 端點，由新的專用端點取代
