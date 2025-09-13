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

from core import key_manager
from tools.gemini_manager import GeminiManager

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()

# --- Pydantic 模型 ---
class KeyRequest(BaseModel):
    api_key: str = Field(..., title="Google API Key")
    name: Optional[str] = Field(None, title="Key Alias")

class TestKeyRequest(BaseModel):
    api_key: str

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

@router.get("/models", summary="獲取所有可用的 AI 模型")
async def get_available_models():
    """
    動態查詢並回傳所有當前可用的 Gemini 模型列表。
    這需要至少有一個有效的 API 金鑰。
    """
    try:
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
