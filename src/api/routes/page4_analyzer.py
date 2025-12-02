# --- 檔案: src/api/routes/page4_analyzer.py ---
import logging
import sqlite3
import sys
import json
import uuid
import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from pydantic import BaseModel

SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from db import database
from api.dependencies import get_db
from core import time_utils

log = logging.getLogger(__name__)
router = APIRouter()

TEMP_JSON_DIR = SRC_DIR.parent / "temp_json"
REPORTS_DIR = SRC_DIR.parent / "reports"
TEMP_JSON_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

import asyncio
import functools

class Stage1Request(BaseModel):
    file_ids: List[int]
    model_name: str
    delay_seconds: float = 0

class Stage1RetryRequest(BaseModel):
    task_id: int
    model_name: str

class PerformanceAnalysisRequest(BaseModel):
    task_ids: List[int]

class DateInferenceRequest(BaseModel):
    task_ids: List[int]
    model_name: str

class Stage2Request(BaseModel):
    task_ids: List[int]
    model_name: str

class SummaryRequest(BaseModel):
    task_ids: List[int]
    model_name: str

def _run_stage1_blocking_task(task_id: int, file_id: int, model_name: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
    log.info(f"第一階段任務實際執行開始：task_id={task_id}, file_id={file_id}, model={model_name}")
    db_conn = None
    try:
        db_conn = database.get_db_connection()
        if not db_conn:
            raise ConnectionError("背景任務無法連線到資料庫。")

        from core import key_manager, prompt_manager
        from tools.gemini_manager import GeminiManager
        from tools.quantitative_analyzer import find_valid_yfinance_symbol
        from tools.taiwan_stock_suffix_helper import SUFFIX_HELPER

        with db_conn:
            gemini = None
            try:
                valid_keys = key_manager.get_all_valid_keys_for_manager(db_conn)
                gemini = GeminiManager(api_keys=valid_keys)
            except ValueError as e:
                error_message = f"AI用戶端初始化失敗，無法執行分析: {e}"
                log.error(f"第一階段任務 task_id={task_id} 因無法初始化 Gemini 用戶端而終止。", exc_info=True)
                database.update_analysis_task(db_conn, task_id=task_id, updates={"stage1_status": "failed", "stage1_error_log": error_message})
                return
            all_prompts = prompt_manager.get_all_prompts()
            prompt_template = all_prompts.get("stage_1_extraction_prompt")
            if not prompt_template:
                raise ValueError("在提示詞庫中找不到 'stage_1_extraction_prompt'。")
            analysis_task_data = database.get_analysis_task(db_conn, task_id=task_id)
            if not analysis_task_data or not analysis_task_data['file_content_for_analysis']:
                raise ValueError(f"分析任務 {task_id} 中找不到可供分析的檔案內容。")
            text_content = analysis_task_data['file_content_for_analysis']
            prompt = prompt_template.format(document_text=text_content)
            database.update_analysis_task(db_conn, task_id=task_id, updates={"stage1_status": "gemini_processing"})

        notification_msg = {"type": "analysis_update", "task_id": task_id, "status": "gemini_processing", "stage": 1, "result": database.get_analysis_task(db_conn, task_id)}
        asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)

        structured_data, error, used_key, token_usage = gemini.prompt_for_json(prompt=prompt, model_name=model_name)
        if error:
            raise error
        with db_conn:
            if used_key and token_usage > 0:
                key_manager.record_token_usage(db_conn, key_name=used_key, tokens_used=token_usage)
        raw_symbol = structured_data.get("symbol")
        corrected_for_tw_symbol = SUFFIX_HELPER.get_corrected_symbol(raw_symbol)
        valid_symbol = find_valid_yfinance_symbol(corrected_for_tw_symbol)
        with db_conn:
            if not valid_symbol:
                error_message = f"AI 提取的股票代號 '{raw_symbol}' (經台灣後綴校正後為 '{corrected_for_tw_symbol}') 無法通過 yfinance 驗證。"
                log.warning(f"任務 {task_id}: {error_message}")
                database.update_analysis_task(db_conn, task_id=task_id, updates={"stage1_status": "validation_failed", "stage1_token_usage": token_usage, "stage1_error_log": error_message})
                json_filename = f"stage1_{task_id}_{uuid.uuid4().hex[:8]}_INVALID.json"
                json_path = TEMP_JSON_DIR / json_filename
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(structured_data, f, ensure_ascii=False, indent=2)
                database.update_analysis_task(db_conn, task_id=task_id, updates={"stage1_json_path": str(json_path)})
                return
            log.info(f"任務 {task_id}: 原始代號 '{raw_symbol}' 最終被校正並驗證為 '{valid_symbol}'。")
            structured_data['symbol'] = valid_symbol
            json_filename = f"stage1_{task_id}_{uuid.uuid4().hex[:8]}.json"
            json_path = TEMP_JSON_DIR / json_filename
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(structured_data, f, ensure_ascii=False, indent=2)
            database.update_analysis_task(db_conn, task_id=task_id, updates={"stage1_status": "completed", "stage1_json_path": str(json_path), "stage1_token_usage": token_usage})
        log.info(f"第一階段任務成功：task_id={task_id}，JSON 已儲存至 {json_path}")
    except Exception as e:
        error_message = f"錯誤: {type(e).__name__}: {str(e)}"
        log.error(f"第一階段任務失敗：task_id={task_id}，{error_message}", exc_info=True)
        if db_conn:
            with db_conn:
                database.update_analysis_task(db_conn, task_id=task_id, updates={"stage1_status": "failed", "stage1_error_log": error_message})
    finally:
        if db_conn:
            db_conn.close()

async def run_analysis_task_wrapper(task_id: int, semaphore: asyncio.Semaphore, blocking_func, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, **kwargs):
    async with semaphore:
        log.info(f"任務 {task_id} 已取得信號量，準備執行...")
        db_conn = database.get_db_connection()
        if not db_conn:
            log.error(f"任務 {task_id}: 無法取得資料庫連線，任務中止。")
            return
        try:
            with db_conn:
                stage = kwargs.get("stage")
                status_field = "status"
                if stage == "performance":
                    status_field = "performance_status"
                    update_payload = {status_field: "processing"}
                elif stage == 'date_inference':
                    status_field = "date_inference_status"
                    update_payload = {status_field: "processing"}
                elif stage == 'summary':
                    status_field = "summary_status"
                    update_payload = {status_field: "processing", "summary_model": kwargs.get("model_name")}
                elif stage in [1, 2]:
                    status_field = f"stage{stage}_status"
                    update_payload = {status_field: "processing", f"stage{stage}_model": kwargs.get("model_name")}
                else:
                    update_payload = {"performance_status": "processing"}
                database.update_analysis_task(db_conn, task_id=task_id, updates=update_payload)
            notification_msg = {"type": "analysis_update", "task_id": task_id, "status": "processing", "stage": stage, "result": database.get_analysis_task(db_conn, task_id)}
            await queue.put(notification_msg)
            func_kwargs = kwargs.copy()
            func_kwargs.pop('stage', None)
            partial_func = functools.partial(blocking_func, task_id=task_id, queue=queue, loop=loop, **func_kwargs)
            await loop.run_in_executor(None, partial_func)
        except Exception as e:
            log.error(f"包裝函式捕獲到未預期的錯誤 (任務 {task_id}): {e}", exc_info=True)
        finally:
            with db_conn:
                log.info(f"任務 {task_id} 執行完畢，釋放信號量。")
                final_task_state = database.get_analysis_task(db_conn, task_id)
                final_status = final_task_state.get(status_field, 'unknown') if final_task_state else 'unknown'
                final_notification_msg = {"type": "analysis_update", "task_type": f"analysis_stage_{stage}", "task_id": task_id, "status": final_status, "result": final_task_state}
            await queue.put(final_notification_msg)
            db_conn.close()

@router.post("/start_stage1_analysis")
async def start_stage1_analysis(request: Request, payload: Stage1Request, background_tasks: BackgroundTasks, db: sqlite3.Connection = Depends(get_db)):
    if not payload.file_ids:
        raise HTTPException(status_code=400, detail="檔案 ID 列表不可為空。")
    semaphore = request.app.state.analysis_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()
    if not semaphore or not queue:
        raise HTTPException(status_code=500, detail="伺服器狀態未完全初始化（缺少佇列或信號量）。")
    tasks_to_run_params = []
    with db:
        for file_id in payload.file_ids:
            file_data = database.get_url_by_id(db, url_id=file_id)
            if not file_data:
                log.warning(f"在啟動第一階段分析時，找不到檔案 ID: {file_id}，已跳過。")
                continue
            filename = Path(file_data['local_path']).name if file_data.get('local_path') else f"未知檔案_{file_id}"
            task = database.create_or_get_analysis_task(db, file_id=file_id, filename=filename)
            if task:
                database.update_analysis_task(db, task_id=task['id'], updates={"stage1_status": "pending", "stage1_error_log": None, "stage1_json_path": None, "performance_status": "pending", "performance_error_log": None, "stage2_status": "pending", "stage2_error_log": None, "stage2_report_path": None})
                tasks_to_run_params.append({"task_id": task['id'], "file_id": file_id, "model_name": payload.model_name})
    async def run_all_tasks_concurrently():
        log.info(f"準備使用 asyncio.gather 併發執行 {len(tasks_to_run_params)} 個分析任務...")
        from core.config_manager import get_config_value
        delay = get_config_value("gemini_submission_delay", 1.0)
        log.info(f"將以 {delay} 秒的間隔，依序執行 {len(tasks_to_run_params)} 個分析任務...")
        for i, params in enumerate(tasks_to_run_params):
            log.info(f"正在提交第 {i+1}/{len(tasks_to_run_params)} 個任務...")
            await run_analysis_task_wrapper(task_id=params['task_id'], semaphore=semaphore, blocking_func=_run_stage1_blocking_task, queue=queue, loop=loop, file_id=params['file_id'], model_name=params['model_name'], stage=1)
            if i < len(tasks_to_run_params) - 1:
                log.info(f"任務提交完畢，等待 {delay} 秒...")
                await asyncio.sleep(delay)
        log.info("所有序列任務均已提交執行。")
    if tasks_to_run_params:
        background_tasks.add_task(run_all_tasks_concurrently)
    return {"message": f"已成功為 {len(tasks_to_run_params)} 個檔案排入第一階段併發分析佇列。"}

@router.get("/files_for_stage1")
async def get_files_for_stage1(db: sqlite3.Connection = Depends(get_db)):
    try:
        processed_files = database.get_urls_by_statuses(db, statuses=['processed'])
        if not processed_files:
            return []
        results = []
        with db:
            for file_row in processed_files:
                file_id = file_row['id']
                filename = Path(file_row['local_path']).name if file_row['local_path'] else f"未知檔案_{file_id}"
                file_hash = file_row['file_hash']
                task_data = database.create_or_get_analysis_task(db, file_id=file_id, filename=filename)
                if task_data:
                    task_data['source_document_id'] = file_id
                    task_data['file_hash'] = file_hash
                    results.append(task_data)
        return results
    except Exception as e:
        log.error(f"API: 獲取待分析檔案列表時出錯: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取待分析檔案列表時發生伺服器內部錯誤。")

@router.get("/files_for_summary")
async def get_files_for_summary_page(db: sqlite3.Connection = Depends(get_db)):
    try:
        processed_files = database.get_urls_by_statuses(db, statuses=['processed', 'processing_failed'])
        if not processed_files:
            return []
        results = []
        with db:
            for file_row in processed_files:
                file_id = file_row['id']
                filename = Path(file_row['local_path']).name if file_row['local_path'] else f"未知檔案_{file_id}"
                task_data = database.create_or_get_analysis_task(db, file_id=file_id, filename=filename)
                if task_data:
                    task_data['title'] = file_row.get('title', filename)
                    task_data['author'] = file_row.get('author')
                    task_data['message_date'] = file_row.get('message_date')
                    results.append(task_data)
        return results
    except Exception as e:
        log.error(f"API: 獲取待摘要檔案列表時出錯: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取待摘要檔案列表時發生伺服器內部錯誤。")

@router.get("/stage1_result/{task_id}")
async def get_stage1_result(task_id: int, db: sqlite3.Connection = Depends(get_db)):
    with db:
        task = database.get_analysis_task(db, task_id=task_id)
    if not task or not task.get("stage1_json_path"):
        raise HTTPException(status_code=404, detail="找不到任務或其第一階段的 JSON 產出。")
    json_path = Path(task["stage1_json_path"])
    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"JSON 檔案遺失於路徑：{json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

class UpdateDateSingleRequest(BaseModel):
    task_id: int
    new_date: str

class UpdateDatesBatchRequest(BaseModel):
    updates: List[UpdateDateSingleRequest]

@router.post("/update_date_single")
async def update_date_single(payload: UpdateDateSingleRequest, db: sqlite3.Connection = Depends(get_db)):
    try:
        with db:
            success = database.update_analysis_task(db, task_id=payload.task_id, updates={"inferred_publish_date": payload.new_date, "date_inference_status": "completed", "date_inference_model": "manual", "date_inference_token_usage": 0})
        if success:
            return {"message": f"任務 #{payload.task_id} 的日期已成功更新。"}
        else:
            raise HTTPException(status_code=500, detail="更新資料庫時發生錯誤。")
    except Exception as e:
        log.error(f"更新單一日期時出錯 (task_id: {payload.task_id}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update_dates_batch")
async def update_dates_batch(payload: UpdateDatesBatchRequest, db: sqlite3.Connection = Depends(get_db)):
    updated_count = 0
    try:
        with db:
            for update in payload.updates:
                success = database.update_analysis_task(db, task_id=update.task_id, updates={"inferred_publish_date": update.new_date, "date_inference_status": "completed", "date_inference_model": "manual_batch", "date_inference_token_usage": 0})
                if success:
                    updated_count += 1
        return {"message": f"成功更新了 {updated_count} / {len(payload.updates)} 個任務的日期。"}
    except Exception as e:
        log.error(f"批次更新日期時出錯: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

from fastapi.responses import FileResponse
import os

class GenerateReportRequest(BaseModel):
    task_ids: List[int]

@router.post("/generate_report", response_class=FileResponse)
async def generate_report_endpoint(payload: GenerateReportRequest, background_tasks: BackgroundTasks, db: sqlite3.Connection = Depends(get_db)):
    if not payload.task_ids:
        raise HTTPException(status_code=400, detail="任務 ID 列表不可為空。")
    try:
        from tools.report_generator_docx import create_docx_report
        task_ids_str = ", ".join(map(str, payload.task_ids))
        log.info(f"API 層：正在為任務 {task_ids_str} 調用報告生成服務...")

        report_path = create_docx_report(task_ids=payload.task_ids, db_conn=db)

        log.info(f"API 層：報告生成服務完成，檔案位於 {report_path}")
        background_tasks.add_task(os.remove, report_path)
        download_filename = f"綜合績效報告_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        return FileResponse(path=report_path, filename=download_filename, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except FileNotFoundError as e:
        log.error(f"生成報告時發生錯誤：找不到必要的檔案。{e}", exc_info=True)
        raise HTTPException(status_code=404, detail=f"找不到生成報告所需的資料檔案：{e}")
    except Exception as e:
        log.error(f"生成報告時發生未預期的伺服器錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成報告時發生內部錯誤: {e}")
