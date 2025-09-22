# --- 檔案: src/api/routes/page4_analyzer.py ---
# --- 說明: 此檔案已於 2025-09-12 重構，以支援兩階段 AI 分析流程。---

import logging
import sys
import json
import uuid
import datetime
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel

# --- 路徑修正與模듈匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 核心模組匯入 ---
# V4 優化：移除 get_client，改為依賴注入
# from db.client import get_client
from db.client import DBClient
from ..dependencies import get_db
# V4 優化：移除 get_db_connection
# from db.database import get_db_connection
# JULES V6 啟動優化：延遲載入重量級依賴
from core import time_utils
# from core import key_manager, prompt_manager
# from tools.gemini_manager import GeminiManager
# from tools.quantitative_analyzer import find_valid_yfinance_symbol
# from tools.taiwan_stock_suffix_helper import SUFFIX_HELPER
from fastapi import Depends

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()
# V4 優化：移除在模組加載時建立的客戶端實例。
# DB_CLIENT = get_client()

# JULES (2025-09-17): 暫時加回 DB_CLIENT 全域變數，以相容舊的整合測試。
# 這些測試使用 monkeypatch 來修補這個變數，但在 V4 重構後它已被移除。
# 長期解決方案是重寫測試以使用 FastAPI 的依賴注入覆蓋機制。
DB_CLIENT = DBClient()

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

# --- WebSocket 通知輔助函式 (已由佇列取代) ---
# JULES (2025-09-13): 移除了舊的 _send_websocket_notification 函式。
# 現在所有通知都將透過一個從主應用程式傳入的 asyncio.Queue 來發送。

# --- 重構後的背景任務函式 (同步阻塞部分) ---
def _run_stage1_blocking_task(task_id: int, file_id: int, model_name: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, db_client: DBClient):
    """
    (V4 優化後) 執行第一階段 AI 分析的同步阻塞部分。
    現在接收一個 db_client 實例，而不是使用全域變數。
    """
    log.info(f"第一階段任務實際執行開始：task_id={task_id}, file_id={file_id}, model={model_name}")
    try:
        # JULES V6 啟動優化：延遲載入
        from core import key_manager, prompt_manager
        from tools.gemini_manager import GeminiManager
        from tools.quantitative_analyzer import find_valid_yfinance_symbol
        from tools.taiwan_stock_suffix_helper import SUFFIX_HELPER

        # 1. 初始化 Gemini Manager
        from core.config_manager import get_config_value
        api_timeout = get_config_value("api_timeout_seconds", 35)

        all_prompts = prompt_manager.get_all_prompts()
        prompt_template = all_prompts.get("stage_1_extraction_prompt")
        if not prompt_template:
            raise ValueError("在提示詞庫中找不到 'stage_1_extraction_prompt'。")

        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")
        gemini = GeminiManager(api_keys=valid_keys, timeout=api_timeout)

        # 2. 從資料庫獲取檔案內容
        analysis_task_data = db_client.get_analysis_task(task_id=task_id)
        if not analysis_task_data or not analysis_task_data['file_content_for_analysis']:
            raise ValueError(f"分析任務 {task_id} 中找不到可供分析的檔案內容 (file_content_for_analysis)。")
        text_content = analysis_task_data['file_content_for_analysis']

        # 3. 執行 AI 資料提取
        prompt = prompt_template.format(document_text=text_content)

        db_client.update_analysis_task(task_id=task_id, updates={"stage1_status": "gemini_processing"})
        notification_msg = {"type": "analysis_update", "task_id": task_id, "status": "gemini_processing", "stage": 1, "result": db_client.get_analysis_task(task_id)}
        asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)

        structured_data, error, used_key, token_usage = gemini.prompt_for_json(prompt=prompt, model_name=model_name)

        if error:
            raise error

        if used_key and token_usage > 0:
            key_manager.record_token_usage(key_name=used_key, tokens_used=token_usage)

        raw_symbol = structured_data.get("symbol")
        corrected_for_tw_symbol = SUFFIX_HELPER.get_corrected_symbol(raw_symbol)
        valid_symbol = find_valid_yfinance_symbol(corrected_for_tw_symbol)

        if not valid_symbol:
            error_message = f"AI 提取的股票代號 '{raw_symbol}' (經台灣後綴校正後為 '{corrected_for_tw_symbol}') 無法通過 yfinance 驗證，也無法在國際市場中找到對應代號。"
            log.warning(f"任務 {task_id}: {error_message}")
            db_client.update_analysis_task(
                task_id=task_id,
                updates={
                    "stage1_status": "validation_failed",
                    "stage1_token_usage": token_usage,
                    "stage1_error_log": error_message
                }
            )
            json_filename = f"stage1_{task_id}_{uuid.uuid4().hex[:8]}_INVALID.json"
            json_path = TEMP_JSON_DIR / json_filename
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(structured_data, f, ensure_ascii=False, indent=2)
            db_client.update_analysis_task(task_id=task_id, updates={"stage1_json_path": str(json_path)})
            return

        log.info(f"任務 {task_id}: 原始代號 '{raw_symbol}' 最終被校正並驗證為 '{valid_symbol}'。")
        structured_data['symbol'] = valid_symbol

        json_filename = f"stage1_{task_id}_{uuid.uuid4().hex[:8]}.json"
        json_path = TEMP_JSON_DIR / json_filename
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(structured_data, f, ensure_ascii=False, indent=2)

        db_client.update_analysis_task(
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
        db_client.update_analysis_task(task_id=task_id, updates={"stage1_status": "failed", "stage1_error_log": error_message})

def _run_date_inference_blocking_task(task_id: int, model_name: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, db_client: DBClient):
    """
    (V4 優化後) 執行 AI 日期推斷的同步阻塞部分。
    (Jules @ 2025-09-17) 優化：優先使用資料庫中的 message_date，若無效或不存在才使用 AI。
    現在接收一個 db_client 實例。
    """
    log.info(f"AI 日期推斷任務實際執行開始：task_id={task_id}")
    try:
        # JULES V6 啟動優化：延遲載入
        from core import key_manager, prompt_manager
        from tools.gemini_manager import GeminiManager

        task_data = db_client.get_analysis_task(task_id=task_id)
        if not task_data or not task_data.get("file_content_for_analysis"):
             raise ValueError(f"任務 {task_id} 中找不到可供分析的檔案內容。")

        url_record = db_client.get_url_by_id(task_data['file_id'])

        # Jules's Change: 優先使用 message_date
        if url_record and url_record.get("message_date"):
            message_date = url_record["message_date"]
            try:
                datetime.datetime.strptime(message_date.strip(), '%Y-%m-%d')
                log.info(f"任務 {task_id}: 找到並使用有效的 message_date: {message_date}，將跳過 AI 日期推斷。")
                db_client.update_analysis_task(
                    task_id=task_id,
                    updates={
                        "inferred_publish_date": message_date.strip(),
                        "date_inference_status": "completed",
                        "date_inference_model": "pre_existing", # 標記來源為既有資料
                        "date_inference_token_usage": 0
                    }
                )
                return # 直接結束函式
            except (ValueError, TypeError):
                log.warning(f"任務 {task_id}: 資料庫中的 message_date ('{message_date}') 格式無效，將繼續使用 AI 推斷。")
        # End of Jules's Change

        all_prompts = prompt_manager.get_all_prompts()
        date_prompt_template = all_prompts.get("stage_1_5_date_inference_prompt")
        if not date_prompt_template:
            raise ValueError("在提示詞庫中找不到 'stage_1_5_date_inference_prompt'。")


        from core.config_manager import get_config_value
        api_timeout = get_config_value("api_timeout_seconds", 35)

        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")
        gemini = GeminiManager(api_keys=valid_keys, timeout=api_timeout)

        text_content = task_data['file_content_for_analysis']

        # Fallback message_date if needed for the prompt itself
        fallback_message_date = url_record.get("message_date", time_utils.get_current_taipei_date_str()) if url_record else time_utils.get_current_taipei_date_str()

        date_prompt = date_prompt_template.format(
            document_text=text_content,
            message_date=fallback_message_date,
            today_date=time_utils.get_current_taipei_date_str()
        )

        inferred_date_str, error, used_key, token_usage = gemini.prompt_for_text(prompt=date_prompt, model_name=model_name)
        if error:
            raise error

        if used_key and token_usage > 0:
            key_manager.record_token_usage(key_name=used_key, tokens_used=token_usage)

        try:
            datetime.datetime.strptime(inferred_date_str.strip(), '%Y-%m-%d')
            inferred_date_to_save = inferred_date_str.strip()
            log.info(f"任務 {task_id}: AI 成功推斷出日期: {inferred_date_to_save}")
        except ValueError:
            log.warning(f"任務 {task_id}: AI 回傳的日期格式無效 ('{inferred_date_str}')。將使用訊息日期作為後備。")
            inferred_date_to_save = fallback_message_date

        db_client.update_analysis_task(
            task_id=task_id,
            updates={
                "inferred_publish_date": inferred_date_to_save,
                "date_inference_status": "completed",
                "date_inference_model": model_name,
                "date_inference_token_usage": token_usage
            }
        )

    except Exception as e:
        error_message = f"錯誤: {type(e).__name__}: {str(e)}"
        log.error(f"AI 日期推斷任務失敗：task_id={task_id}，{error_message}", exc_info=True)
        db_client.update_analysis_task(task_id=task_id, updates={"date_inference_status": "failed", "performance_error_log": error_message})


def _run_performance_analysis_blocking_task(task_id: int, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, db_client: DBClient):
    """
    (V4 優化後) 執行績效分析的同步阻塞部分。
    現在接收一個 db_client 實例。
    """
    log.info(f"本地績效分析任務實際執行開始：task_id={task_id}")
    try:
        # JULES V6 啟動優化：延遲載入
        from tools.quantitative_analyzer import calculate_performance_stats

        task_data = db_client.get_analysis_task(task_id=task_id)
        if not task_data or not task_data.get("stage1_json_path"):
            raise ValueError(f"找不到任務 {task_id} 或其第一階段的 JSON 產出路徑。")

        json_path = Path(task_data["stage1_json_path"])
        if not json_path.exists():
            raise FileNotFoundError(f"第一階段的 JSON 檔案不存在於路徑：{json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            stage1_data = json.load(f)

        if not isinstance(stage1_data, dict):
            raise TypeError(f"第一階段產出的 JSON 不是預期的字典格式，而是 {type(stage1_data)}。")

        symbol = stage1_data.get("symbol")
        if not symbol:
            raise ValueError("第一階段產出的 JSON 中缺少 'symbol' 資訊。")

        if task_data.get("inferred_publish_date"):
            start_date = task_data["inferred_publish_date"]
            log.info(f"任務 {task_id}: 使用 AI 推斷的發布日期: {start_date}")
        else:
            url_record = db_client.get_url_by_id(task_data['file_id'])
            start_date = url_record.get("message_date") if url_record else None
            log.warning(f"任務 {task_id}: 未找到 AI 推斷日期，回退使用訊息日期: {start_date}")

        if not start_date:
            raise ValueError(f"任務 {task_id}: 缺少可用的起始日期 (推斷或訊息日期)，無法執行量化分析。")

        log.info(f"任務 {task_id}: 正在為代號 {symbol} (起始日: {start_date}) 執行量化分析...")
        from core.config_manager import get_config_value
        api_timeout = get_config_value("api_timeout_seconds", 35)
        performance_results = calculate_performance_stats(symbol, start_date, timeout=api_timeout)
        stage1_data["performance_analysis"] = performance_results

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(stage1_data, f, ensure_ascii=False, indent=2)

        db_client.update_analysis_task(task_id=task_id, updates={"performance_status": "completed"})
        log.info(f"績效分析任務成功：task_id={task_id}")

    except Exception as e:
        error_message = f"錯誤: {type(e).__name__}: {str(e)}"
        log.error(f"績效分析任務失敗：task_id={task_id}，{error_message}", exc_info=True)
        db_client.update_analysis_task(task_id=task_id, updates={"performance_status": "failed", "performance_error_log": error_message})


def _run_stage2_blocking_task(task_id: int, model_name: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, db_client: DBClient):
    """
    (V4 優化後) 執行第二階段 AI 分析的同步阻塞部分。
    現在接收一個 db_client 實例。
    """
    log.info(f"第二階段任務實際執行開始：task_id={task_id}, model={model_name}")
    try:
        # JULES V6 啟動優化：延遲載入
        from core import key_manager, prompt_manager
        from tools.gemini_manager import GeminiManager

        task_data = db_client.get_analysis_task(task_id=task_id)
        if not task_data or not task_data.get("stage1_json_path"):
            raise ValueError(f"找不到任務 {task_id} 或其第一階段的 JSON 產出路徑。")
        json_path = Path(task_data["stage1_json_path"])
        if not json_path.exists():
            raise FileNotFoundError(f"第一階段的 JSON 檔案不存在於路徑：{json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            structured_data = json.load(f)

        from core.config_manager import get_config_value
        api_timeout = get_config_value("api_timeout_seconds", 35)

        all_prompts = prompt_manager.get_all_prompts()
        prompt_template = all_prompts.get("stage_2_generation_prompt")
        if not prompt_template:
            raise ValueError("在提示詞庫中找不到 'stage_2_generation_prompt'。")
        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")
        gemini = GeminiManager(api_keys=valid_keys, timeout=api_timeout)

        prompt = prompt_template.format(data_package=json.dumps(structured_data, ensure_ascii=False, indent=2))

        db_client.update_analysis_task(task_id=task_id, updates={"stage2_status": "gemini_processing"})
        notification_msg = {"type": "analysis_update", "task_id": task_id, "status": "gemini_processing", "stage": 2, "result": db_client.get_analysis_task(task_id)}
        asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)

        report_html, error, used_key, token_usage = gemini.prompt_for_text(prompt=prompt, model_name=model_name)

        if error:
            raise error

        if used_key and token_usage > 0:
            key_manager.record_token_usage(key_name=used_key, tokens_used=token_usage)

        report_filename = f"report_{task_id}_{uuid.uuid4().hex[:8]}.html"
        report_path = REPORTS_DIR / report_filename
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_html)

        db_client.update_analysis_task(
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
        db_client.update_analysis_task(task_id=task_id, updates={"stage2_status": "failed", "stage2_error_log": error_message})


def _run_summary_generation_blocking_task(task_id: int, model_name: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, db_client: DBClient):
    """
    (Jules @ 2025-09-21) 執行「重點摘要」生成的同步阻塞部分。
    """
    log.info(f"重點摘要任務實際執行開始：task_id={task_id}, model={model_name}")
    try:
        # JULES V6 啟動優化：延遲載入
        from core import key_manager, prompt_manager
        from tools.gemini_manager import GeminiManager

        task_data = db_client.get_analysis_task(task_id=task_id)
        if not task_data or not task_data.get("file_content_for_analysis"):
            raise ValueError(f"找不到任務 {task_id} 或其可供分析的內容。")

        text_content = task_data['file_content_for_analysis']

        from core.config_manager import get_config_value
        api_timeout = get_config_value("api_timeout_seconds", 35)

        all_prompts = prompt_manager.get_all_prompts()
        prompt_template = all_prompts.get("summary_generation_prompt")
        if not prompt_template:
            # 如果找不到專用提示詞，則使用一個通用的後備提示詞
            log.warning("在提示詞庫中找不到 'summary_generation_prompt'，將使用通用摘要提示詞。")
            prompt_template = "請為以下文件生成一段約 200-300 字的簡潔中文摘要：\n\n{document_text}"


        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")
        gemini = GeminiManager(api_keys=valid_keys, timeout=api_timeout)

        prompt = prompt_template.format(document_text=text_content)

        db_client.update_analysis_task(task_id=task_id, updates={"summary_status": "gemini_processing"})
        # JULES (2025-09-22): 修正通知訊息，使其與其他分析階段的格式一致，包含 status 和 stage。
        notification_msg = {"type": "analysis_update", "task_id": task_id, "status": "gemini_processing", "stage": "summary", "result": db_client.get_analysis_task(task_id)}
        asyncio.run_coroutine_threadsafe(queue.put(notification_msg), loop)

        summary_content, error, used_key, token_usage = gemini.prompt_for_text(prompt=prompt, model_name=model_name)

        if error:
            raise error

        if used_key and token_usage > 0:
            key_manager.record_token_usage(key_name=used_key, tokens_used=token_usage)

        db_client.update_analysis_task(
            task_id=task_id,
            updates={
                "summary_status": "completed",
                "summary_content": summary_content,
                "summary_token_usage": token_usage,
                "summary_model": model_name
            }
        )
        log.info(f"重點摘要任務成功：task_id={task_id}")

    except Exception as e:
        error_message = f"錯誤: {type(e).__name__}: {str(e)}"
        log.error(f"重點摘要任務失敗：task_id={task_id}，{error_message}", exc_info=True)
        db_client.update_analysis_task(task_id=task_id, updates={"summary_status": "failed", "summary_error_log": error_message})


# --- 新的非同步包裝函式 (用於併發控制) ---
async def run_analysis_task_wrapper(task_id: int, semaphore: asyncio.Semaphore, blocking_func, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, db_client: DBClient, **kwargs):
    """
    (V4 優化後) 一個通用的非同步包裝函式，用於控制併發並執行阻塞的分析任務。
    現在接收一個 db_client 實例並將其傳遞下去。
    JULES (2025-09-22): 新增 asyncio.wait_for 以防止執行緒無限期掛起。
    """
    async with semaphore:
        log.info(f"任務 {task_id} 已取得信號量，準備執行...")

        stage = kwargs.get("stage")
        status_field = "status" # 預設
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

        db_client.update_analysis_task(task_id=task_id, updates=update_payload)

        notification_msg = {"type": "analysis_update", "task_id": task_id, "status": "processing", "stage": stage, "result": db_client.get_analysis_task(task_id)}
        await queue.put(notification_msg)

        try:
            func_kwargs = kwargs.copy()
            func_kwargs.pop('stage', None)

            partial_func = functools.partial(blocking_func, task_id=task_id, queue=queue, loop=loop, db_client=db_client, **func_kwargs)
            # 使用 wait_for 新增超時保護，防止永久掛起
            # 超時時間設定為 200 秒，比 GeminiManager 內部的 180 秒略長
            await asyncio.wait_for(
                loop.run_in_executor(None, partial_func),
                timeout=200.0
            )
        except asyncio.TimeoutError:
            error_message = "任務執行超時 (超過 200 秒)，可能在與 AI 服務通訊時發生問題。"
            log.error(f"任務 {task_id}: {error_message}")
            db_client.update_analysis_task(task_id=task_id, updates={status_field: "failed", "stage1_error_log": error_message, "stage2_error_log": error_message, "summary_error_log": error_message})
        except Exception as e:
            log.error(f"包裝函式捕獲到未預期的錯誤 (任務 {task_id}): {e}", exc_info=True)
            # 在此處也應更新狀態為失敗，以防萬一
            db_client.update_analysis_task(task_id=task_id, updates={status_field: "failed", "stage1_error_log": str(e), "stage2_error_log": str(e), "summary_error_log": str(e)})
        finally:
            log.info(f"任務 {task_id} 執行完畢或超時，釋放信號量。")
            final_task_state = db_client.get_analysis_task(task_id)
            final_status = final_task_state.get(status_field, 'unknown')
            final_notification_msg = {"type": "analysis_update", "task_type": f"analysis_stage_{stage}", "task_id": task_id, "status": final_status, "result": final_task_state}
            await queue.put(final_notification_msg)

# --- 新的 API 端點 ---

@router.post("/start_stage1_analysis")
async def start_stage1_analysis(request: Request, payload: Stage1Request, background_tasks: BackgroundTasks, db: DBClient = Depends(get_db)):
    """(V5 優化後) 啟動第一階段：JSON 提取，採用併發調度"""
    if not payload.file_ids:
        raise HTTPException(status_code=400, detail="檔案 ID 列表不可為空。")

    semaphore = request.app.state.analysis_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()

    if not semaphore or not queue:
        raise HTTPException(status_code=500, detail="伺服器狀態未完全初始化（缺少佇列或信號量）。")

    # 步驟 1: 在一個快速、非阻塞的迴圈中準備所有任務
    tasks_to_run_params = []
    for file_id in payload.file_ids:
        file_data = db.get_url_by_id(url_id=file_id)
        if not file_data:
            log.warning(f"在啟動第一階段分析時，找不到檔案 ID: {file_id}，已跳過。")
            continue

        filename = Path(file_data['local_path']).name if file_data.get('local_path') else f"未知檔案_{file_id}"
        task = db.create_or_get_analysis_task(file_id=file_id, filename=filename)

        if task:
            # 重設任務狀態
            db.update_analysis_task(task_id=task['id'], updates={
                "stage1_status": "pending", "stage1_error_log": None, "stage1_json_path": None,
                "performance_status": "pending", "performance_error_log": None,
                "stage2_status": "pending", "stage2_error_log": None, "stage2_report_path": None
            })
            tasks_to_run_params.append({
                "task_id": task['id'],
                "file_id": file_id,
                "model_name": payload.model_name
            })

    # 步驟 2: 定義一個非同步函式，用於收集並併發執行所有任務
    async def run_all_tasks_concurrently():
        log.info(f"準備使用 asyncio.gather 併發執行 {len(tasks_to_run_params)} 個分析任務...")
        coroutines = []
        for params in tasks_to_run_params:
            coro = run_analysis_task_wrapper(
                task_id=params['task_id'],
                semaphore=semaphore,
                blocking_func=_run_stage1_blocking_task,
                queue=queue,
                loop=loop,
                db_client=db,
                file_id=params['file_id'],
                model_name=params['model_name'],
                stage=1
            )
            coroutines.append(coro)

        # JULES (2025-09-17): 根據使用者需求，將併發改為可設定延遲的序列執行
        from core.config_manager import get_config_value
        delay = get_config_value("gemini_submission_delay", 1.0) # 預設延遲 1 秒
        log.info(f"將以 {delay} 秒的間隔，依序執行 {len(coroutines)} 個分析任務...")

        for i, coro in enumerate(coroutines):
            log.info(f"正在提交第 {i+1}/{len(coroutines)} 個任務...")
            await coro
            if i < len(coroutines) - 1:
                log.info(f"任務提交完畢，等待 {delay} 秒...")
                await asyncio.sleep(delay)

        log.info("所有序列任務均已提交執行。")

    # 步驟 3: 將這個統一的併發執行函式作為單一背景任務加入
    if tasks_to_run_params:
        background_tasks.add_task(run_all_tasks_concurrently)

    return {"message": f"已成功為 {len(tasks_to_run_params)} 個檔案排入第一階段併發分析佇列。"}


@router.post("/retry_stage1_analysis")
async def retry_stage1_analysis(request: Request, payload: Stage1RetryRequest, background_tasks: BackgroundTasks, db: DBClient = Depends(get_db)):
    """(V4 優化後) 重試單一失敗的第一階段分析任務"""
    semaphore = request.app.state.analysis_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()

    if not semaphore or not queue:
        raise HTTPException(status_code=500, detail="伺服器狀態未完全初始化（缺少佇列或信號量）。")

    task = db.get_analysis_task(task_id=payload.task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"找不到任務 ID: {payload.task_id}")

    db.update_analysis_task(
        task_id=payload.task_id,
        updates={
            "stage1_status": "pending",
            "stage1_error_log": None,
            "stage1_json_path": None,
            "stage1_token_usage": None,
            "stage1_model": None,
            "date_inference_status": "pending",
            "performance_status": "pending",
            "stage2_status": "pending",
        }
    )

    background_tasks.add_task(
        run_analysis_task_wrapper,
        task_id=task['id'],
        semaphore=semaphore,
        blocking_func=_run_stage1_blocking_task,
        queue=queue,
        loop=loop,
        db_client=db,  # V4 優化：傳入共享的 db 實例
        file_id=task['file_id'],
        model_name=payload.model_name,
        stage=1
    )

    return {"message": f"已成功為任務 #{payload.task_id} 排入重試佇列。"}


@router.post("/start_date_inference")
async def start_date_inference(request: Request, payload: DateInferenceRequest, background_tasks: BackgroundTasks, db: DBClient = Depends(get_db)):
    """(V4 優化後) 啟動 AI 日期推斷"""
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
            blocking_func=_run_date_inference_blocking_task,
            queue=queue,
            loop=loop,
            db_client=db,  # V4 優化：傳入共享的 db 實例
            model_name=payload.model_name,
            stage="date_inference"
        )

    return {"message": f"已成功為 {len(payload.task_ids)} 個任務排入日期推斷佇列。"}


@router.post("/start_performance_analysis")
async def start_performance_analysis(request: Request, payload: PerformanceAnalysisRequest, background_tasks: BackgroundTasks, db: DBClient = Depends(get_db)):
    """(V4 優化後) 啟動本地績效分析"""
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
            db_client=db,  # V4 優化：傳入共享的 db 實例
            stage="performance"
        )

    return {"message": f"已成功為 {len(payload.task_ids)} 個任務排入績效分析佇列。"}

@router.post("/start_stage2_analysis")
async def start_stage2_analysis(request: Request, payload: Stage2Request, background_tasks: BackgroundTasks, db: DBClient = Depends(get_db)):
    """(V4 優化後) 啟動第二階段：報告生成"""
    if not payload.task_ids:
        raise HTTPException(status_code=400, detail="任務 ID 列表不可為空。")

    semaphore = request.app.state.analysis_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()

    if not semaphore or not queue:
        raise HTTPException(status_code=500, detail="伺服器狀態未完全初始化（缺少佇列或信號量）。")

    for task_id in payload.task_ids:
        task_data = db.get_analysis_task(task_id=task_id)
        if task_data and task_data.get('performance_status') == 'completed':
            background_tasks.add_task(
                run_analysis_task_wrapper,
                task_id=task_id,
                semaphore=semaphore,
                blocking_func=_run_stage2_blocking_task,
                queue=queue,
                loop=loop,
                db_client=db,  # V4 優化：傳入共享的 db 實例
                model_name=payload.model_name,
                stage=2
            )
        else:
            log.warning(f"跳過任務 ID {task_id} 的第二階段分析，因為其績效分析未完成。")

    return {"message": f"已為 {len(payload.task_ids)} 個符合條件的任務啟動第二階段分析。"}


@router.post("/start_summary_generation")
async def start_summary_generation(request: Request, payload: SummaryRequest, background_tasks: BackgroundTasks, db: DBClient = Depends(get_db)):
    """(Jules @ 2025-09-21) 啟動重點摘要生成"""
    if not payload.task_ids:
        raise HTTPException(status_code=400, detail="任務 ID 列表不可為空。")

    semaphore = request.app.state.analysis_semaphore
    queue = request.app.state.notification_queue
    loop = asyncio.get_running_loop()

    if not semaphore or not queue:
        raise HTTPException(status_code=500, detail="伺服器狀態未完全初始化（缺少佇列或信號量）。")

    for task_id in payload.task_ids:
        # 重設狀態以允許重新生成
        db.update_analysis_task(task_id=task_id, updates={
            "summary_status": "pending",
            "summary_content": None,
            "summary_error_log": None,
            "summary_token_usage": None,
            "summary_model": None
        })
        background_tasks.add_task(
            run_analysis_task_wrapper,
            task_id=task_id,
            semaphore=semaphore,
            blocking_func=_run_summary_generation_blocking_task,
            queue=queue,
            loop=loop,
            db_client=db,
            model_name=payload.model_name,
            stage="summary"
        )

    return {"message": f"已為 {len(payload.task_ids)} 個任務啟動重點摘要生成。"}


@router.get("/files_for_stage1")
async def get_files_for_stage1(db: DBClient = Depends(get_db)):
    """(V4 優化後) 獲取所有已處理、可供第一階段分析的檔案列表。"""
    try:
        processed_files = db.get_urls_by_statuses(statuses=['processed'])

        if not processed_files:
            return []

        results = []
        for file_row in processed_files:
            file_id = file_row['id']
            filename = Path(file_row['local_path']).name if file_row['local_path'] else f"未知檔案_{file_id}"
            file_hash = file_row['file_hash']

            task_data = db.create_or_get_analysis_task(file_id=file_id, filename=filename)

            if task_data:
                task_data['source_document_id'] = file_id
                task_data['file_hash'] = file_hash
                results.append(task_data)

        return results
    except Exception as e:
        log.error(f"API: 獲取待分析檔案列表時出錯: {e}", exc_info=True)
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail="獲取待分析檔案列表時發生伺服器內部錯誤。")

@router.get("/files_for_date_inference")
async def get_files_for_date_inference(db: DBClient = Depends(get_db)):
    """(V4 優化後) 獲取所有已完成第一階段的任務，供日期推斷頁面顯示。"""
    tasks = db.get_all_analysis_tasks()
    return [t for t in tasks if t.get('stage1_status') == 'completed']

@router.get("/files_for_performance_analysis")
async def get_files_for_performance_analysis(db: DBClient = Depends(get_db)):
    """(V4 優化後) 獲取所有已完成日期推斷的任務，供績效分析頁面顯示。"""
    tasks = db.get_all_analysis_tasks()
    return [t for t in tasks if t.get('date_inference_status') == 'completed']

@router.get("/files_for_summary")
async def get_files_for_summary_page(db: DBClient = Depends(get_db)):
    """
    (Jules @ 2025-09-21) 獲取所有可供生成「重點摘要」的檔案列表。
    這包括所有已成功完成「檔案處理」的項目。
    """
    try:
        # 邏輯與 get_files_for_stage1 相似，因為它們都是分析流程的起點
        processed_files = db.get_urls_by_statuses(statuses=['processed', 'processing_failed'])

        if not processed_files:
            return []

        results = []
        for file_row in processed_files:
            file_id = file_row['id']
            filename = Path(file_row['local_path']).name if file_row['local_path'] else f"未知檔案_{file_id}"

            # 為每個檔案獲取或創建對應的分析任務記錄
            task_data = db.create_or_get_analysis_task(file_id=file_id, filename=filename)

            if task_data:
                # 附加原始文件資訊以便在 UI 中顯示
                task_data['title'] = file_row.get('title', filename)
                task_data['author'] = file_row.get('author')
                task_data['message_date'] = file_row.get('message_date')
                results.append(task_data)

        return results
    except Exception as e:
        log.error(f"API: 獲取待摘要檔案列表時出錯: {e}", exc_info=True)
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail="獲取待摘要檔案列表時發生伺服器內部錯誤。")


@router.get("/files_for_stage2")
async def get_files_for_stage2(db: DBClient = Depends(get_db)):
    """(V4 優化後) 獲取已完成績效分析，可供生成報告的任務列表。"""
    tasks = db.get_all_analysis_tasks()
    return [t for t in tasks if t.get('performance_status') == 'completed']


@router.get("/stage1_result/{task_id}")
async def get_stage1_result(task_id: int, db: DBClient = Depends(get_db)):
    """(V4 優化後) 獲取指定任務第一階段產出的 JSON 內容"""
    task = db.get_analysis_task(task_id=task_id)
    if not task or not task.get("stage1_json_path"):
        raise HTTPException(status_code=404, detail="找不到任務或其第一階段的 JSON 產出。")

    json_path = Path(task["stage1_json_path"])
    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"JSON 檔案遺失於路徑：{json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

@router.get("/stage1_5_result/{task_id}")
async def get_stage1_5_result(task_id: int, db: DBClient = Depends(get_db)):
    """(V4 優化後) 獲取指定任務日期推斷的 JSON 結果"""
    task = db.get_analysis_task(task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="找不到指定的任務。")

    return {
        "task_id": task.get("id"),
        "status": task.get("date_inference_status"),
        "inferred_publish_date": task.get("inferred_publish_date"),
        "model": task.get("date_inference_model"),
        "token_usage": task.get("date_inference_token_usage"),
        "error_log": task.get("date_inference_error_log")
    }

@router.get("/stage2_result/{task_id}")
async def get_stage2_result(task_id: int, db: DBClient = Depends(get_db)):
    """(V4 優化後) 獲取指定任務績效分析的 JSON 結果"""
    task = db.get_analysis_task(task_id=task_id)
    if not task or not task.get("stage1_json_path"):
        raise HTTPException(status_code=404, detail="找不到任務或其 JSON 產出。")

    json_path = Path(task["stage1_json_path"])
    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"JSON 檔案遺失於路徑：{json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("performance_analysis", {"detail": "在 JSON 中找不到績效分析結果。"})


# --- 已棄用的舊版分析流程 ---
# 移除了 /analysis_status 和 /processed_files 端點，由新的專用端點取代

# JULES (2025-09-17): 為日期校正工作台新增後端 API
class UpdateDateSingleRequest(BaseModel):
    task_id: int
    new_date: str

class UpdateDatesBatchRequest(BaseModel):
    updates: List[UpdateDateSingleRequest]

@router.post("/update_date_single")
async def update_date_single(payload: UpdateDateSingleRequest, db: DBClient = Depends(get_db)):
    """手動更新單一任務的日期。"""
    try:
        success = db.update_analysis_task(
            task_id=payload.task_id,
            updates={
                "inferred_publish_date": payload.new_date,
                "date_inference_status": "completed",
                "date_inference_model": "manual",
                "date_inference_token_usage": 0
            }
        )
        if success:
            return {"message": f"任務 #{payload.task_id} 的日期已成功更新。"}
        else:
            raise HTTPException(status_code=500, detail="更新資料庫時發生錯誤。")
    except Exception as e:
        log.error(f"更新單一日期時出錯 (task_id: {payload.task_id}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update_dates_batch")
async def update_dates_batch(payload: UpdateDatesBatchRequest, db: DBClient = Depends(get_db)):
    """批次更新多個任務的日期。"""
    updated_count = 0
    try:
        for update in payload.updates:
            success = db.update_analysis_task(
                task_id=update.task_id,
                updates={
                    "inferred_publish_date": update.new_date,
                    "date_inference_status": "completed",
                    "date_inference_model": "manual_batch",
                    "date_inference_token_usage": 0
                }
            )
            if success:
                updated_count += 1
        return {"message": f"成功更新了 {updated_count} / {len(payload.updates)} 個任務的日期。"}
    except Exception as e:
        log.error(f"批次更新日期時出錯: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# JULES (2025-09-17): 新增用於生成 Word 報告的 API 端點
from fastapi.responses import FileResponse
from tools.report_generator_docx import create_docx_report
import os

class GenerateReportRequest(BaseModel):
    task_ids: List[int]

@router.post("/generate_report", response_class=FileResponse)
async def generate_report_endpoint(
    payload: GenerateReportRequest,
    background_tasks: BackgroundTasks,
    db: DBClient = Depends(get_db)
):
    """
    接收一個或多個分析任務 ID，呼叫服務層生成一份包含這些報告的 Word (.docx) 文件，
    並將其作為檔案下載回傳。
    """
    if not payload.task_ids:
        raise HTTPException(status_code=400, detail="任務 ID 列表不可為空。")

    try:
        # 步驟 1: 呼叫服務層函式來生成報告
        task_ids_str = ", ".join(map(str, payload.task_ids))
        log.info(f"API 層：正在為任務 {task_ids_str} 調用報告生成服務...")

        report_path = create_docx_report(task_ids=payload.task_ids, db_client=db)

        log.info(f"API 層：報告生成服務完成，檔案位於 {report_path}")

        # 步驟 2: 設定一個背景任務，在檔案回傳後將其刪除
        background_tasks.add_task(os.remove, report_path)

        # 步驟 3: 使用 FileResponse 回傳檔案
        download_filename = f"綜合績效報告_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"

        return FileResponse(
            path=report_path,
            filename=download_filename,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except FileNotFoundError as e:
        log.error(f"生成報告時發生錯誤：找不到必要的檔案。{e}", exc_info=True)
        raise HTTPException(status_code=404, detail=f"找不到生成報告所需的資料檔案：{e}")
    except Exception as e:
        log.error(f"生成報告時發生未預期的伺服器錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成報告時發生內部錯誤: {e}")
