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
        # 如果檔案不存在，建立一個空的
        PROMPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}
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
    """獲取所有提示詞。"""
    return _load_prompts()

def get_prompt_by_key(key: str) -> Optional[Dict[str, Any]]:
    """根據鍵名獲取單一提示詞。"""
    prompts = _load_prompts()
    return prompts.get(key)

def add_or_update_prompt(key: str, content: Dict[str, Any]) -> Dict[str, Any]:
    """
    新增或更新一個提示詞。
    :param key: 提示詞的唯一鍵名。
    :param content: 提示詞的內容，應為一個字典。
    :return: 新增或更新後的提示詞。
    """
    if not key or not key.strip():
        raise ValueError("提示詞的鍵名不可為空。")
    if not isinstance(content, dict):
        raise TypeError("提示詞內容必須是一個有效的字典 (JSON 物件)。")

    prompts = _load_prompts()
    prompts[key] = content
    _save_prompts(prompts)
    return {key: content}

def delete_prompt(key: str) -> bool:
    """根據鍵名刪除一個提示詞。"""
    prompts = _load_prompts()
    if key in prompts:
        del prompts[key]
        _save_prompts(prompts)
        return True
    return False
