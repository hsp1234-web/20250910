# src/tools/trading_analyzer.py
import logging
import sys
from pathlib import Path
import json
import requests

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from db.analysis_manager import update_analysis_task
from db.database import get_db_connection
from core.key_manager import get_valid_key
from core.prompt_manager import get_prompt
from tools.gemini_processor import call_gemini_api

log = logging.getLogger(__name__)

def notify_frontend(task_id: int, status: str, message: str, progress: int):
    """
    呼叫內部 API 來觸發 WebSocket 更新。
    """
    try:
        # TODO: The port should ideally not be hardcoded.
        # It can be fetched from a config file or discovered at runtime.
        url = "http://127.0.0.1:8001/api/internal/notify_status"
        payload = {
            "taskId": task_id,
            "status": status,
            "message": message,
            "progress": progress
        }
        requests.post(url, json=payload, timeout=5)
    except requests.RequestException as e:
        log.error(f"無法通知前端任務 {task_id} 的更新: {e}")

def run_trading_analysis(task_id: int):
    """
    執行完整的、基於藍圖的交易分析流程。
    目前只實作第一階段：結構化資訊提取。
    """
    log.info(f"分析流程開始，任務 ID: {task_id}")
    conn = None
    try:
        # 步驟 0: 初始化
        notify_frontend(task_id, "PROCESSING", "任務開始，正在初始化...", 5)

        conn = get_db_connection()
        cursor = conn.cursor()

        # 步驟 1: 獲取任務所需資料
        cursor.execute("SELECT source_document_id FROM analysis_tasks WHERE id = ?", (task_id,))
        task_data = cursor.fetchone()
        if not task_data:
            raise ValueError(f"在資料庫中找不到分析任務 ID: {task_id}")

        source_document_id = task_data['source_document_id']
        cursor.execute("SELECT extracted_text, extracted_image_paths FROM extracted_urls WHERE id = ?", (source_document_id,))
        doc_data = cursor.fetchone()
        if not doc_data:
            raise ValueError(f"在資料庫中找不到原始文件 ID: {source_document_id}")

        text_content = doc_data['extracted_text'] or ""
        image_paths = json.loads(doc_data['extracted_image_paths'] or "[]")

        log.info(f"[任務 {task_id}]：成功獲取原始文件內容。")
        notify_frontend(task_id, "STAGE_1_EXTRACTING", "獲取原始文件成功，準備呼叫 AI...", 15)

        # 步驟 2: 獲取提示詞與 API 金鑰
        prompt_key = "trading_strategy_poc_v2"
        prompt_template = get_prompt(prompt_key)
        if not prompt_template:
            raise ValueError(f"找不到指定的提示詞: {prompt_key}")

        api_key = get_valid_key()
        if not api_key:
            raise ValueError("金鑰池中沒有任何有效的 API 金鑰。")

        # 步驟 3: 執行第一階段 AI - 結構化資訊提取
        log.info(f"[任務 {task_id}]：開始呼叫 Gemini API 進行結構化資訊提取。")
        notify_frontend(task_id, "STAGE_1_EXTRACTING", "正在呼叫 AI 進行分析...", 25)

        # 將文件內容填入提示詞模板
        full_prompt = prompt_template.format(document_text=text_content)

        # 呼叫 Gemini API
        ai_response_str = call_gemini_api(api_key, full_prompt, image_paths)

        log.info(f"[任務 {task_id}]：AI 回應接收完畢，正在解析...")
        notify_frontend(task_id, "STAGE_1_EXTRACTING", "AI 回應接收完畢，正在解析...", 75)

        # 步驟 4: 解析並儲存結果
        # Gemini API 有時會回傳被 ` ```json ` 和 ` ``` ` 包裹的字串
        if ai_response_str.strip().startswith("```json"):
            ai_response_str = ai_response_str.strip()[7:-3].strip()

        try:
            stage1_result = json.loads(ai_response_str)
        except json.JSONDecodeError:
            log.error(f"[任務 {task_id}]：AI 回應不是有效的 JSON 格式。回應內容: {ai_response_str}")
            raise ValueError("AI 回應不是有效的 JSON 格式。")

        update_analysis_task(task_id, {"stage1_result_json": json.dumps(stage1_result, ensure_ascii=False)})
        log.info(f"[任務 {task_id}]：第一階段結果已成功儲存至資料庫。")

        # 步驟 5: 完成
        update_analysis_task(task_id, {"status": "COMPLETE"})
        notify_frontend(task_id, "COMPLETE", "✅ 分析完成！", 100)
        log.info(f"✅ 分析流程成功完成，任務 ID: {task_id}")

    except Exception as e:
        log.error(f"❌ 分析流程發生嚴重錯誤，任務 ID: {task_id} - 錯誤: {e}", exc_info=True)
        # 更新任務狀態為錯誤，並記錄錯誤訊息
        update_analysis_task(task_id, {"status": "ERROR", "error_message": str(e)})
        notify_frontend(task_id, "ERROR", f"分析失敗: {e}", 100)
    finally:
        if conn:
            conn.close()
