# src/api/routes/page7_prompts.py
import logging
import sys
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Request

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from core import prompt_manager

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()

# --- API 端點 ---

@router.get("/prompts", summary="獲取所有兩階段提示詞")
async def get_all_prompts_endpoint():
    """
    獲取 `default_prompts.json` 中的所有提示詞。
    回傳一個包含 'stage_1_extraction_prompt' 和 'stage_2_generation_prompt' 的物件。
    """
    try:
        return prompt_manager.get_all_prompts()
    except Exception as e:
        log.error(f"獲取提示詞時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="讀取提示詞檔案時發生伺服器內部錯誤。")

@router.post("/prompts", summary="儲存所有兩階段提示詞")
async def save_all_prompts_endpoint(request: Request):
    """
    接收一個包含 'stage_1_extraction_prompt' 和 'stage_2_generation_prompt' 的物件，
    並將其完整儲存。
    """
    try:
        prompts_data = await request.json()
        prompt_manager.save_prompts(prompts_data)
        return {"message": "所有提示詞已成功儲存。"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"儲存提示詞時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="儲存提示詞檔案時發生伺服器內部錯誤。")
