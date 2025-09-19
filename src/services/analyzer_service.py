import redis
import json
import logging
import sys
import threading
import time
from pathlib import Path
import uuid

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from db.client import DBClient
from core import key_manager, prompt_manager
from tools.gemini_manager import GeminiManager
from tools.quantitative_analyzer import find_valid_yfinance_symbol
from tools.taiwan_stock_suffix_helper import SUFFIX_HELPER
from core.config_manager import get_config_value

# --- 設定 ---
log = logging.getLogger(__name__)
db_client = DBClient()

REDIS_HOST = "localhost"
REDIS_PORT = 6379
PROCESSING_COMPLETE_CHANNEL = "tasks:processing_complete"

TEMP_JSON_DIR = SRC_DIR.parent / "temp_json"
TEMP_JSON_DIR.mkdir(exist_ok=True)


def analyze_from_message(message_data: dict):
    """
    (V7 重構後) 根據從 Redis 收到的訊息執行第一階段 AI 分析。
    此版本不再依賴舊的 analysis_tasks 表，而是直接更新主任務的 result 欄位。
    """
    task_id = message_data.get("task_id")
    payload = message_data.get("payload", {})
    text_content = payload.get("extracted_text")
    original_filename = payload.get("original_filename")

    if not all([task_id, text_content, original_filename]):
        log.error(f"[Analyzer] 訊息格式錯誤，缺少必要欄位: {message_data}")
        return

    log.info(f"[Analyzer] 開始分析任務 {task_id}，來源檔案: {original_filename}")
    db_client.update_task_status(task_id, "analyzing", {"detail": "AI 分析處理中..."})

    try:
        # 1. 初始化 Gemini Manager
        api_timeout = get_config_value("api_timeout_seconds", 35)
        model_name = "gemini-1.5-flash-latest" # JULES: 暫時寫死，未來可從訊息或設定中讀取

        all_prompts = prompt_manager.get_all_prompts()
        prompt_template = all_prompts.get("stage_1_extraction_prompt")
        if not prompt_template:
            raise ValueError("在提示詞庫中找不到 'stage_1_extraction_prompt'。")

        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")
        gemini = GeminiManager(api_keys=valid_keys, timeout=api_timeout)

        # 2. 執行 AI 資料提取
        prompt = prompt_template.format(document_text=text_content)

        structured_data, error, used_key, token_usage = gemini.prompt_for_json(prompt=prompt, model_name=model_name)

        if error:
            raise error

        if used_key and token_usage > 0:
            key_manager.record_token_usage(key_name=used_key, tokens_used=token_usage)

        # 3. 驗證股票代號
        raw_symbol = structured_data.get("symbol")
        corrected_for_tw_symbol = SUFFIX_HELPER.get_corrected_symbol(raw_symbol)
        valid_symbol = find_valid_yfinance_symbol(corrected_for_tw_symbol)

        if not valid_symbol:
            error_message = f"AI 提取的股票代號 '{raw_symbol}' (校正後 '{corrected_for_tw_symbol}') 無法通過 yfinance 驗證。"
            raise ValueError(error_message)

        log.info(f"[Analyzer] 任務 {task_id}: 原始代號 '{raw_symbol}' 最終驗證為 '{valid_symbol}'。")
        structured_data['symbol'] = valid_symbol

        # 4. 儲存結果 JSON 檔案
        json_filename = f"analysis_{task_id}.json"
        json_path = TEMP_JSON_DIR / json_filename
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(structured_data, f, ensure_ascii=False, indent=2)

        # 5. 更新主任務的 result 欄位
        # 首先獲取現有的 result，以附加新資訊而不是覆蓋
        task_record = db_client.get_task_status(task_id)
        current_result = json.loads(task_record.get("result", "{}"))

        # 添加分析結果
        analysis_result = {
            "analysis_json_path": str(json_path),
            "analysis_token_usage": token_usage,
            "analysis_model": model_name,
            "validated_symbol": valid_symbol
        }
        current_result.update(analysis_result)

        db_client.update_task_status(task_id, "analysis_complete", current_result)
        log.info(f"[Analyzer] 第一階段分析成功：task_id={task_id}")

    except Exception as e:
        error_message = f"錯誤: {type(e).__name__}: {str(e)}"
        log.error(f"[Analyzer] 第一階段分析失敗：task_id={task_id}，{error_message}", exc_info=True)
        db_client.update_task_status(task_id, "analysis_failed", {"error": error_message})


def start_redis_analyzer_listener():
    """
    啟動 Redis 監聽器，用於接收已完成處理的任務。
    """
    log.info("[Analyzer] 啟動 Redis 監聽器，準備接收處理完成的任務...")

    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
    pubsub = redis_client.pubsub()
    pubsub.subscribe(PROCESSING_COMPLETE_CHANNEL)

    log.info(f"[Analyzer] 已訂閱頻道: {PROCESSING_COMPLETE_CHANNEL}")

    for message in pubsub.listen():
        if message['type'] == 'message':
            log.info(f"[Analyzer] 從 Redis 收到新訊息！")
            try:
                message_data = json.loads(message['data'])
                log.debug(f"訊息內容: {message_data}")
                # 啟動新執行緒處理分析，避免阻塞監聽迴圈
                analysis_thread = threading.Thread(target=analyze_from_message, args=(message_data,))
                analysis_thread.start()
            except json.JSONDecodeError:
                log.error(f"[Analyzer] 無法解析收到的訊息: {message['data']}")
            except Exception as e:
                log.error(f"[Analyzer] 處理訊息時發生未預期錯誤: {e}", exc_info=True)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log.info("正在獨立模式下啟動分析器服務...")
    start_redis_analyzer_listener()
