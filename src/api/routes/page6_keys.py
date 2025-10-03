# src/api/routes/page6_keys.py
import logging
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from core import config_manager
from core.key_lifecycle_manager import key_lifecycle_manager
# JULES V6 啟動優化：延遲載入
# from tools.gemini_manager import GeminiManager

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()

# --- Pydantic 模型 ---
class TestKeyRequest(BaseModel):
    api_key: str

# --- API 端點 ---

@router.get("/status", summary="獲取所有金鑰的即時狀態")
async def get_keys_status():
    """
    從 KeyLifecycleManager 獲取所有金鑰的當前狀態。
    這是一個即時的記憶體狀態反映，用於前端展示。
    """
    return key_lifecycle_manager.get_key_status()

@router.get("/models", summary="獲取所有可用的 AI 模型")
async def get_available_models():
    """
    動態查詢並回傳所有當前可用的 Gemini 模型列表。
    這需要至少有一個有效的 API 金鑰。
    """
    try:
        # JULES V6 啟動優化：延遲載入
        from tools.gemini_manager import GeminiManager
        # 從新的管理器獲取一個有效的金鑰
        valid_key = key_lifecycle_manager.get_valid_gemini_key()
        if not valid_key:
            raise HTTPException(status_code=400, detail="沒有可用的有效 API 金鑰來查詢模型。")

        gemini = GeminiManager(api_keys=[valid_key])
        models = gemini.list_available_models()
        return models
    except HTTPException:
        # 確保 FastAPI 的 HTTP 例外能被直接拋出，而不是被下面的通用 Exception 捕捉
        raise
    except ValueError as e:
        # 可能是金鑰池為空，或 GeminiManager 初始化失敗
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"查詢可用模型時發生未預期的錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢可用模型時發生意外錯誤: {str(e)}")

# --- JULES (2025-09-17): 重構為通用的設定管理 API ---

class ConfigUpdateRequest(BaseModel):
    value: float = Field(..., description="要更新的設定值。")

@router.get("/config/{key}", summary="獲取指定的設定值")
async def get_config_value_api(key: str):
    """
    從設定檔中讀取並回傳指定鍵的值。
    """
    try:
        value = config_manager.get_config_value(key)
        if value is None:
            raise HTTPException(status_code=404, detail=f"找不到設定鍵: {key}")
        return {"key": key, "value": value}
    except Exception as e:
        log.error(f"讀取設定 '{key}' 時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"無法讀取設定檔: {key}")

@router.post("/config/{key}", summary="更新指定的設定值")
async def update_config_value_api(key: str, payload: ConfigUpdateRequest):
    """
    更新設定檔中的指定鍵值對。
    """
    try:
        # 在此處可以加入對特定 key 的值進行驗證的邏輯
        if key in ["api_timeout_seconds", "gemini_submission_delay", "gemini_rotation_delay"]:
            if not (0 <= payload.value <= 300):
                raise HTTPException(status_code=400, detail="設定值必須介於 0 到 300 之間。")

        if key == "api_max_retries":
            # 確保重試次數是整數且在合理範圍內
            if not (isinstance(payload.value, int) or payload.value.is_integer()):
                 raise HTTPException(status_code=400, detail="重試次數必須是整數。")
            if not (0 <= int(payload.value) <= 5):
                raise HTTPException(status_code=400, detail="重試次數必須介於 0 到 5 之間。")
            # 將浮點數轉為整數儲存
            payload.value = int(payload.value)

        success = config_manager.update_config_value(key, payload.value)
        if success:
            return {"message": f"設定 '{key}' 已成功更新。", "new_value": payload.value}
        else:
            raise HTTPException(status_code=500, detail="儲存設定檔時發生錯誤。")
    except HTTPException as e:
        raise e # 重新拋出 HTTP 例外
    except Exception as e:
        log.error(f"更新設定 '{key}' 時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新設定時發生伺服器內部錯誤: {key}")
