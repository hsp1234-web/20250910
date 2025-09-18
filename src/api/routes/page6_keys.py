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

from core import key_manager, config_manager
# JULES V6 啟動優化：延遲載入
# from tools.gemini_manager import GeminiManager

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()

# --- Pydantic 模型 ---
class KeyRequest(BaseModel):
    api_key: str = Field(..., title="Google API Key")
    name: Optional[str] = Field(None, title="Key Alias")

class TestKeyRequest(BaseModel):
    api_key: str

class LoadFromEnvRequest(BaseModel):
    count: int = Field(..., ge=0, le=20, title="要載入的金鑰數量")

# --- API 端點 ---

@router.get("", summary="獲取所有金鑰的狀態")
async def get_keys_status():
    """
    獲取所有已儲存金鑰的列表，包含其雜湊值和有效性狀態。
    出於安全考量，此端點不會回傳原始金鑰。
    """
    return key_manager.get_all_keys()

@router.post("", summary="新增並驗證一個 API 金鑰")
async def add_new_key(payload: KeyRequest):
    """
    將一個新的 API 金鑰新增到金鑰池，並立即對其進行驗證。
    """
    try:
        result = key_manager.add_key(payload.api_key, payload.name)
        return {"message": f"金鑰 '{result['name']}' 已新增。", **result}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        log.error(f"新增金鑰時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="新增金鑰時發生伺服器內部錯誤。")

@router.delete("/{key_hash}", summary="刪除指定的 API 金鑰")
async def remove_key(key_hash: str):
    """
    根據金鑰的雜湊值，從金鑰池中將其刪除。
    """
    if key_manager.delete_key(key_hash):
        return {"message": "金鑰已成功刪除。"}
    else:
        raise HTTPException(status_code=404, detail="找不到具有該雜湊值的金鑰。")

@router.post("/validate", summary="重新驗證所有金鑰")
async def validate_all_stored_keys():
    """
    觸發對金鑰池中所有金鑰的重新驗證。
    這是一個耗時操作，客戶端應準備等待。
    """
    try:
        validated_keys = key_manager.validate_all_keys()
        return {"message": "所有金鑰已重新驗證。", "keys": validated_keys}
    except Exception as e:
        log.error(f"重新驗證金鑰時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="重新驗證金鑰時發生伺服器內部錯誤。")

@router.post("/load_from_authorized_source", summary="從授權來源（環境變數）載入金鑰")
async def load_keys_from_env(payload: LoadFromEnvRequest):
    """
    從伺服器環境變數中讀取 GOOGLE_API_KEY... 系列金鑰並新增至金鑰池。
    """
    try:
        result_summary = key_manager.add_keys_from_environment(payload.count)
        return {"message": "從授權來源載入金鑰完成。", "summary": result_summary}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"從環境變數載入金鑰時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="從環境變數載入金鑰時發生伺服器內部錯誤。")

@router.get("/models", summary="獲取所有可用的 AI 模型")
async def get_available_models():
    """
    動態查詢並回傳所有當前可用的 Gemini 模型列表。
    這需要至少有一個有效的 API 金鑰。
    """
    try:
        # JULES V6 啟動優化：延遲載入
        from tools.gemini_manager import GeminiManager
        # 獲取有效的金鑰來初始化 Gemini Manager
        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise HTTPException(status_code=400, detail="沒有可用的有效 API 金鑰來查詢模型。")

        gemini = GeminiManager(api_keys=valid_keys)
        models = gemini.list_available_models()
        return models
    except ValueError as e:
        # 可能是金鑰池為空
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"查詢可用模型時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢可用模型時發生意外錯誤: {str(e)}")

@router.post("/test", summary="測試一個 API 金鑰的有效性")
async def test_api_key(payload: TestKeyRequest):
    """
    測試提供的 API 金鑰是否有效，但不會將其儲存到金鑰池。
    """
    try:
        is_valid = key_manager.test_key(payload.api_key)
        return {"is_valid": is_valid}
    except Exception as e:
        log.error(f"測試金鑰時發生錯誤: {e}", exc_info=True)
        # 即使是測試，也回傳一個明確的失敗狀態，而不是 500 錯誤
        return {"is_valid": False, "error": str(e)}

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
