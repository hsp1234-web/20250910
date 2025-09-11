# src/api/routes/page7_prompts.py
import logging
import sys
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from core import prompt_manager

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()

# --- Pydantic 模型 ---
class PromptRequest(BaseModel):
    key: str = Field(..., title="提示詞的唯一鍵名")
    content: Dict[str, Any] = Field(..., title="提示詞的 JSON 內容")

# --- API 端點 ---

@router.get("/prompts", summary="獲取所有提示詞")
async def get_all_prompts_endpoint():
    """
    獲取 `default_prompts.json` 中的所有提示詞。
    """
    return prompt_manager.get_all_prompts()

@router.post("/prompts", summary="新增或更新一個提示詞")
async def add_or_update_prompt_endpoint(payload: PromptRequest):
    """
    新增一個提示詞。如果鍵名已存在，則會覆蓋現有的內容。
    """
    try:
        result = prompt_manager.add_or_update_prompt(payload.key, payload.content)
        return {"message": f"提示詞 '{payload.key}' 已成功儲存。", "prompt": result}
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"儲存提示詞時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="儲存提示詞時發生伺服器內部錯誤。")

@router.delete("/prompts/{key}", summary="刪除指定的提示詞")
async def delete_prompt_endpoint(key: str):
    """
    根據鍵名刪除一個提示詞。
    """
    if prompt_manager.delete_prompt(key):
        return {"message": f"提示詞 '{key}' 已成功刪除。"}
    else:
        raise HTTPException(status_code=404, detail=f"找不到鍵名為 '{key}' 的提示詞。")
