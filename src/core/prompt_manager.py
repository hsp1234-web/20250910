# src/core/prompt_manager.py
import json
import sys
from pathlib import Path
from typing import Dict, Any

# --- 路徑修正 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 常數 ---
PROMPTS_FILE = SRC_DIR / "prompts" / "default_prompts.json"

def _load_prompts() -> Dict[str, Any]:
    """從 JSON 檔案載入提示詞。"""
    if not PROMPTS_FILE.is_file():
        # 如果檔案不存在，建立一個包含預設結構的檔案
        PROMPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        default_prompts = {
            "stage_1_extraction_prompt": "請在此處定義您的第一階段提取提示詞。",
            "stage_2_generation_prompt": "請在此處定義您的第二階段生成提示詞。"
        }
        with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_prompts, f, indent=4, ensure_ascii=False)
        return default_prompts
    try:
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def _save_prompts(prompts: Dict[str, Any]):
    """將提示詞儲存到 JSON 檔案。"""
    PROMPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(prompts, f, indent=4, ensure_ascii=False)

def get_all_prompts() -> Dict[str, Any]:
    """獲取所有提示詞（現在是一個包含兩個階段提示詞的物件）。"""
    return _load_prompts()

def save_prompts(prompts_data: Dict[str, Any]):
    """
    儲存整個提示詞物件。
    (JULES V7): 移除對特定鍵的驗證，使其成為一個通用的儲存函式。
    """
    if not isinstance(prompts_data, dict):
        raise ValueError("提供的資料格式不正確，必須是一個字典。")

    _save_prompts(prompts_data)
