# -*- coding: utf-8 -*-
"""
================================================
|
|   `index_generator.py`
|
|   **功能**:
|   負責將第一階段 AI 分析產出的詳細 JSON，
|   進一步濃縮成一個精簡的「索引」物件。
|
|   **核心函式**:
|   - `generate_concise_index`:
|     接收一個分析任務 ID，讀取其第一階段
|     的 JSON 產出，使用 Gemini API 和特定
|     的提示詞，生成一個包含核心標題、標籤
|     和極簡摘要的索引 JSON 檔案。
|
|   **設計**:
|   - 完全整合現有的 `GeminiManager` 和
|     `prompt_manager`，確保 API 金鑰和
|     提示詞的統一管理。
|   - 將生成的索引檔案儲存在獨立的 `temp_index/`
|     目錄中，方便管理和追蹤。
|
|   **版本**: 1.0
|   **日期**: 2025-09-21
|
================================================
"""
import logging
import json
import uuid
from pathlib import Path
from typing import Dict, Any

# --- 路徑修正與模組匯入 ---
# 確保能從 src 目錄下正確匯入模組
SRC_DIR = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(SRC_DIR))

from core import key_manager, prompt_manager
from tools.gemini_manager import GeminiManager
from db.client import DBClient
from core.config_manager import get_config_value

# --- 常數與設定 ---
log = logging.getLogger(__name__)
TEMP_INDEX_DIR = SRC_DIR.parent / "temp_index"

# 確保索引目錄存在
TEMP_INDEX_DIR.mkdir(exist_ok=True)


def generate_concise_index(task_id: int, db_client: DBClient) -> str:
    """
    為指定的分析任務生成精簡索引。

    此函式會讀取任務第一階段的 JSON 輸出，
    使用 Gemini API 將其濃縮成一個索引物件，
    並將該索引儲存為新的 JSON 檔案。

    Args:
        task_id (int): 要處理的 analysis_tasks 表中的任務 ID。
        db_client (DBClient): 用於與資料庫互動的客戶端實例。

    Returns:
        str: 成功生成的索引檔案的路徑。

    Raises:
        FileNotFoundError: 如果找不到第一階段的 JSON 檔案。
        ValueError: 如果 API 金鑰或提示詞未設定，或 API 回傳錯誤。
        Exception: 其他未預期的錯誤。
    """
    log.info(f"索引生成任務開始：task_id={task_id}")

    # 1. 從資料庫獲取第一階段的 JSON 路徑
    task_data = db_client.get_analysis_task(task_id=task_id)
    if not task_data or not task_data.get("stage1_json_path"):
        raise FileNotFoundError(f"在任務 {task_id} 中找不到 stage1_json_path。")

    stage1_json_path = Path(task_data["stage1_json_path"])
    if not stage1_json_path.exists():
        raise FileNotFoundError(f"第一階段的 JSON 檔案不存在於路徑：{stage1_json_path}")

    # 2. 讀取 JSON 內容
    with open(stage1_json_path, "r", encoding="utf-8") as f:
        stage1_json_content = json.load(f)

    # 3. 初始化 Gemini Manager 和提示詞
    all_prompts = prompt_manager.get_all_prompts()
    prompt_template = all_prompts.get("stage_1_7_indexing_prompt")
    if not prompt_template:
        raise ValueError("在提示詞庫中找不到 'stage_1_7_indexing_prompt'。")

    valid_keys = key_manager.get_all_valid_keys_for_manager()
    if not valid_keys:
        raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")

    api_timeout = get_config_value("api_timeout_seconds", 35)
    gemini = GeminiManager(api_keys=valid_keys, timeout=api_timeout)

    # 4. 格式化提示詞並呼叫 API
    prompt = prompt_template.format(stage1_json=json.dumps(stage1_json_content, ensure_ascii=False, indent=2))

    # 對於索引生成，我們使用一個較輕量的模型
    model_name = "gemini-2.0-flash-lite"

    log.info(f"正在為任務 {task_id} 呼叫 Gemini API (模型: {model_name}) 以生成索引...")
    index_data, error, used_key, token_usage = gemini.prompt_for_json(prompt=prompt, model_name=model_name)

    if error:
        log.error(f"為任務 {task_id} 生成索引時 API 返回錯誤: {error}")
        raise ValueError(f"API 呼叫失敗: {error}")

    if used_key and token_usage > 0:
        key_manager.record_token_usage(key_name=used_key, tokens_used=token_usage)
        log.info(f"任務 {task_id} 的索引生成消耗了 {token_usage} tokens (使用金鑰: {used_key})。")

    # 5. 儲存生成的索引檔案
    index_filename = f"index_{task_id}_{uuid.uuid4().hex[:8]}.json"
    index_path = TEMP_INDEX_DIR / index_filename
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    log.info(f"任務 {task_id} 的精簡索引已成功生成並儲存至：{index_path}")

    return str(index_path)
