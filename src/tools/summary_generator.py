# -*- coding: utf-8 -*-
"""
================================================
|
|   `summary_generator.py`
|
|   **功能**:
|   負責為已處理的文件生成「小作文」式的重點摘要。
|
|   **核心函式**:
|   - `generate_summary_essay`:
|     接收一個分析任務的資料，讀取其原始文字和
|     所有圖片，使用 Gemini Vision API 和特定
|     的提示詞，透過一次性的多模態呼叫，生成
|     一段精華摘要。
|
|   **設計**:
|   - 採用單一、多模態請求，將文字和圖片一併
|     傳送給 AI，以獲得最高效、最全面的分析。
|   - 完全整合現有的 `GeminiManager`，重用其
|     金鑰管理和 API 呼叫邏輯。
|
|   **版本**: 1.0
|   **日期**: 2025-09-21
|
================================================
"""
import logging
import json
from pathlib import Path
from typing import Dict, Any, List

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(SRC_DIR))

try:
    from PIL import Image
except ImportError:
    Image = None
    logging.warning("Pillow 未安裝，圖片處理功能將被禁用。")

from core import key_manager, prompt_manager
from tools.gemini_manager import GeminiManager
from db.client import DBClient
from core.config_manager import get_config_value

# --- 常數與設定 ---
log = logging.getLogger(__name__)
DOWNLOADS_DIR = SRC_DIR.parent / "downloads"

def generate_summary_essay(task: Dict[str, Any], db_client: DBClient, model_name: str) -> (str, int):
    """
    為指定的分析任務生成「小作文」重點摘要。

    此函式會讀取任務的原始文字和關聯圖片，
    使用 Gemini Vision API 將其濃縮成一段文字摘要。

    Args:
        task (Dict[str, Any]): 包含任務資訊的字典。
        db_client (DBClient): 用於與資料庫互動的客戶端實例。
        model_name (str): 要使用的 Gemini 模型名稱。

    Returns:
        tuple[str, int]: 一個包含 (摘要文字, token消耗量) 的元組。

    Raises:
        ValueError: 如果 API 金鑰或提示詞未設定，或 API 回傳錯誤。
        Exception: 其他未預期的錯誤。
    """
    task_id = task.get("id")
    log.info(f"重點摘要生成任務開始：task_id={task_id}")

    # 1. 獲取文字和圖片路徑
    text_content = task.get("file_content_for_analysis")
    if not text_content:
        raise ValueError(f"任務 {task_id} 中找不到可供分析的文字內容 (file_content_for_analysis)。")

    # 從資料庫獲取原始的 extracted_urls 紀錄以找到圖片路徑
    url_record = db_client.get_url_by_id(task['file_id'])
    image_paths_str = url_record.get("extracted_image_paths") if url_record else None

    image_paths = []
    if image_paths_str:
        try:
            image_paths = json.loads(image_paths_str)
        except json.JSONDecodeError:
            log.warning(f"無法解析任務 {task_id} 的圖片路徑 JSON 字串。")
            image_paths = []

    # 2. 準備多模態請求內容
    prompt_parts = []

    # 載入並加入提示詞
    all_prompts = prompt_manager.get_all_prompts()
    prompt_template = all_prompts.get("prompt_summary_essay")
    if not prompt_template:
        raise ValueError("在提示詞庫中找不到 'prompt_summary_essay'。")
    prompt_parts.append(prompt_template)

    # 加入文字內容
    prompt_parts.append("\n\n--- 以下是文章全文 ---\n")
    prompt_parts.append(text_content)

    # 加入圖片內容
    if image_paths and Image:
        prompt_parts.append("\n\n--- 以下是文章中包含的圖片 ---\n")
        for img_rel_path in image_paths:
            img_full_path = DOWNLOADS_DIR / img_rel_path
            if img_full_path.exists():
                try:
                    img = Image.open(img_full_path)
                    prompt_parts.append(img)
                except Exception as e:
                    log.warning(f"無法開啟或處理圖片 {img_full_path}，已跳過：{e}")
            else:
                log.warning(f"找不到圖片檔案 {img_full_path}，已跳過。")

    # 3. 初始化 Gemini Manager 並呼叫 API
    valid_keys = key_manager.get_all_valid_keys_for_manager()
    if not valid_keys:
        raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")

    api_timeout = get_config_value("api_timeout_seconds", 35)
    gemini = GeminiManager(api_keys=valid_keys, timeout=api_timeout)

    log.info(f"正在為任務 {task_id} 呼叫 Gemini Vision API (模型: {model_name}) 以生成摘要...")

    # 使用 prompt_for_text 因為我們期望的是純文字的「小作文」
    summary_text, error, used_key, token_usage = gemini.prompt_for_text(
        prompt=prompt_parts,
        model_name=model_name
    )

    if error:
        log.error(f"為任務 {task_id} 生成摘要時 API 返回錯誤: {error}")
        raise ValueError(f"API 呼叫失敗: {error}")

    if used_key and token_usage > 0:
        key_manager.record_token_usage(key_name=used_key, tokens_used=token_usage)
        log.info(f"任務 {task_id} 的摘要生成消耗了 {token_usage} tokens (使用金鑰: {used_key})。")

    log.info(f"任務 {task_id} 的重點摘要已成功生成。")

    return summary_text, token_usage
