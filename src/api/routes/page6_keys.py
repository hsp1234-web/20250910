# src/api/routes/page6_keys.py
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import BaseModel, Field

SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from core import key_manager, config_manager
from api.dependencies import get_db

log = logging.getLogger(__name__)
router = APIRouter()

class KeyRequest(BaseModel):
    api_key: str = Field(..., title="API Key Value")
    name: Optional[str] = Field(None, title="Key Alias")
    key_type: str = Field("gemini", title="Key Type", description="金鑰的類型，可以是 'gemini' 或 'fred'。")

class TestKeyRequest(BaseModel):
    api_key: str

class LoadFromEnvRequest(BaseModel):
    count: int = Field(..., ge=0, le=20, title="要載入的金鑰數量")

@router.get("", summary="獲取所有金鑰的狀態")
async def get_keys_status(db: sqlite3.Connection = Depends(get_db)):
    return key_manager.get_all_keys(db)

@router.post("", summary="新增並驗證一個 API 金鑰")
async def add_new_key(payload: KeyRequest, db: sqlite3.Connection = Depends(get_db)):
    try:
        result = key_manager.add_key(db, key_value=payload.api_key, key_name=payload.name, key_type=payload.key_type)
        return {"message": f"類型為 '{payload.key_type}' 的金鑰 '{result['name']}' 已新增。", **result}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        log.error(f"新增金鑰時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="新增金鑰時發生伺服器內部錯誤。")

@router.delete("/{key_hash}", summary="刪除指定的 API 金鑰")
async def remove_key(key_hash: str, db: sqlite3.Connection = Depends(get_db)):
    if key_manager.delete_key(db, key_hash):
        return {"message": "金鑰已成功刪除。"}
    else:
        raise HTTPException(status_code=404, detail="找不到具有該雜湊值的金鑰。")

@router.post("/validate", summary="重新驗證所有金鑰")
def validate_all_stored_keys(db: sqlite3.Connection = Depends(get_db)):
    try:
        validated_keys = key_manager.validate_all_keys(db)
        return {"message": "所有金鑰已重新驗證。", "keys": validated_keys}
    except Exception as e:
        log.error(f"重新驗證金鑰時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="重新驗證金鑰時發生伺服器內部錯誤。")

@router.post("/load_from_authorized_source", summary="從授權來源（環境變數）載入金鑰")
async def load_keys_from_env(payload: LoadFromEnvRequest, db: sqlite3.Connection = Depends(get_db)):
    try:
        result_summary = key_manager.add_keys_from_environment(db, payload.count)
        return {"message": "從授權來源載入金鑰完成。", "summary": result_summary}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"從環境變數載入金鑰時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="從環境變數載入金鑰時發生伺服器內部錯誤。")

@router.get("/models", summary="獲取所有可用的 AI 模型")
async def get_available_models(db: sqlite3.Connection = Depends(get_db)):
    try:
        from tools.gemini_manager import GeminiManager
        valid_keys = key_manager.get_all_valid_keys_for_manager(db)
        if not valid_keys:
            raise HTTPException(status_code=400, detail="沒有可用的有效 API 金鑰來查詢模型。")
        gemini = GeminiManager(api_keys=valid_keys)
        models = gemini.list_available_models()
        return models
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"查詢可用模型時發生未預期的錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢可用模型時發生意外錯誤: {str(e)}")

@router.get("/gemini_status", summary="獲取有效的 Gemini 金鑰數量")
async def get_gemini_key_status(db: sqlite3.Connection = Depends(get_db)):
    try:
        valid_gemini_keys = key_manager.get_all_valid_keys_for_manager(db)
        return {"valid_gemini_key_count": len(valid_gemini_keys)}
    except Exception as e:
        log.error(f"查詢有效 Gemini 金鑰數量時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查詢金鑰狀態時發生伺服器內部錯誤。")

@router.post("/test", summary="測試一個 API 金鑰的有效性")
async def test_api_key(payload: TestKeyRequest):
    try:
        is_valid = key_manager.test_key(payload.api_key)
        return {"is_valid": is_valid}
    except Exception as e:
        log.error(f"測試金鑰時發生錯誤: {e}", exc_info=True)
        return {"is_valid": False, "error": str(e)}

class ConfigUpdateRequest(BaseModel):
    value: float = Field(..., description="要更新的設定值。")

@router.get("/config/{key}", summary="獲取指定的設定值")
async def get_config_value_api(key: str):
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
    try:
        if key in ["api_timeout_seconds", "gemini_submission_delay", "gemini_rotation_delay"]:
            if not (0 <= payload.value <= 300):
                raise HTTPException(status_code=400, detail="設定值必須介於 0 到 300 之間。")
        if key == "api_max_retries":
            if not (isinstance(payload.value, int) or payload.value.is_integer()):
                 raise HTTPException(status_code=400, detail="重試次數必須是整數。")
            if not (0 <= int(payload.value) <= 5):
                raise HTTPException(status_code=400, detail="重試次數必須介於 0 到 5 之間。")
            payload.value = int(payload.value)
        success = config_manager.update_config_value(key, payload.value)
        if success:
            return {"message": f"設定 '{key}' 已成功更新。", "new_value": payload.value}
        else:
            raise HTTPException(status_code=500, detail="儲存設定檔時發生錯誤。")
    except HTTPException as e:
        raise e
    except Exception as e:
        log.error(f"更新設定 '{key}' 時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新設定時發生伺服器內部錯誤: {key}")
