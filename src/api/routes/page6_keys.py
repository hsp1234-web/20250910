# src/api/routes/page6_keys.py
import logging
import sys
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

# 使用重構後的 key_manager 實例
from core.key_manager import key_manager
from core import config_manager
from tools.gemini_manager import GeminiManager

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()

# --- Pydantic 模型 ---
class ManualKeyRequest(BaseModel):
    api_key: str = Field(..., title="Google API Key")
    # JULES: 在新系統中，名稱是必要的，不再是可選的
    name: str = Field(..., title="金鑰別名 (例如 Manual-Key-1)")

class UpdateKeyStatusRequest(BaseModel):
    status: str = Field(..., title="新的金鑰狀態 (active 或 disabled)")

class LoadFromEnvRequest(BaseModel):
    count: int = Field(..., ge=0, le=20, title="要載入的金鑰數量")

# --- API 端點 (已全部更新以使用新的 KeyManager) ---

@router.get("", summary="獲取所有金鑰的狀態")
async def get_keys_status():
    """
    從資料庫獲取所有金鑰的列表及其當前狀態。
    """
    try:
        return key_manager.get_key_statuses()
    except Exception as e:
        log.error(f"獲取金鑰狀態時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取金鑰狀態時發生伺服器內部錯誤。")

@router.post("", summary="手動新增一個 API 金鑰")
async def add_manual_key(payload: ManualKeyRequest):
    """
    將一個新的 API 金鑰手動新增到系統中。
    """
    try:
        success = key_manager.add_key_manually(key_name=payload.name, key_value=payload.api_key)
        if success:
            return {"message": f"金鑰 '{payload.name}' 已成功注入系統。"}
        else:
            raise HTTPException(status_code=500, detail="注入金鑰時發生未知錯誤。")
    except Exception as e:
        log.error(f"新增手動金鑰時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="新增手動金鑰時發生伺服器內部錯誤。")

@router.put("/{key_name}/status", summary="更新指定金鑰的狀態")
async def update_key_status(key_name: str, payload: UpdateKeyStatusRequest):
    """
    手動更新一個金鑰的狀態，主要用於從 UI 停用 (disable) 或重新啟用 (active) 金鑰。
    """
    try:
        success = key_manager.update_key_status(key_name, payload.status)
        if success:
            return {"message": f"金鑰 '{key_name}' 的狀態已更新為 '{payload.status}'。"}
        else:
            raise HTTPException(status_code=404, detail=f"找不到名為 '{key_name}' 的金鑰或更新失敗。")
    except Exception as e:
        log.error(f"更新金鑰 '{key_name}' 狀態時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新金鑰狀態時發生伺服器內部錯誤。")

@router.post("/reset_all", summary="重設所有金鑰為活躍狀態")
async def reset_all_keys():
    """
    將所有處於 'cooldown' 或 'disabled' 狀態的金鑰全部重設為 'active'。
    這是一個方便的管理工具，用於快速恢復整個金鑰池。
    """
    try:
        success = key_manager.reset_all_keys_status()
        if success:
            return {"message": "已成功重設所有金鑰的狀態為 'active'。"}
        else:
            raise HTTPException(status_code=500, detail="重設金鑰狀態時發生錯誤。")
    except Exception as e:
        log.error(f"重設所有金鑰時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="重設金鑰時發生伺服器內部錯誤。")

@router.post("/load_from_authorized_source", summary="從授權來源（環境變數）同步金鑰")
async def load_keys_from_env(payload: LoadFromEnvRequest):
    """
    從伺服器環境變數中讀取 GOOGLE_API_KEY... 系列金鑰並同步至系統。
    """
    try:
        result_summary = key_manager.sync_keys_from_environment(payload.count)
        return {"message": "從授權來源同步金鑰完成。", "summary": result_summary}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"從環境變數載入金鑰時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="從環境變數載入金鑰時發生伺服器內部錯誤。")

@router.get("/models", summary="獲取所有可用的 AI 模型")
async def get_available_models():
    """
    動態查詢並回傳所有當前可用的 Gemini 模型列表。
    此操作會自動從金鑰池中選取一個可用金鑰來執行。
    """
    try:
        # 新的 GeminiManager 不再需要手動傳入金鑰
        gemini = GeminiManager()
        models = gemini.list_available_models()
        # 為了與前端相容，將字串列表轉換為物件列表
        return [{"id": name, "name": name} for name in models]
    except ConnectionError as e:
        # 當 KeyManager 報告金鑰池枯竭時，會引發此錯誤
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"查詢可用模型時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢可用模型時發生意外錯誤: {str(e)}")

# --- 已棄用的端點 ---
# /test 端點已被移除，因為新架構鼓勵直接使用金鑰，透過冷卻機制來處理無效金鑰。
# /delete 端點已被 PUT /{key_name}/status 取代，透過將狀態設為 'disabled' 來實現類似功能。

# --- JULES (2025-09-15): 設定相關的 API 端點保持不變 ---
class TimeoutUpdateRequest(BaseModel):
    timeout: int = Field(..., ge=5, le=300, description="API 請求的超時秒數，範圍 5-300。")

@router.get("/config/timeout", summary="獲取 API 超時設定")
async def get_api_timeout():
    """
    從設定檔中讀取並回傳目前的 API 超時秒數。
    """
    try:
        timeout = config_manager.get_config_value("api_timeout_seconds", default=35)
        return {"timeout": timeout}
    except Exception as e:
        log.error(f"讀取超時設定時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法讀取設定檔。")

@router.post("/config/timeout", summary="更新 API 超時設定")
async def update_api_timeout(payload: TimeoutUpdateRequest):
    """
    更新設定檔中的 API 超時秒數。
    """
    try:
        success = config_manager.update_config_value("api_timeout_seconds", payload.timeout)
        if success:
            return {"message": "API 超時設定已成功更新。", "new_timeout": payload.timeout}
        else:
            raise HTTPException(status_code=500, detail="儲存設定檔時發生錯誤。")
    except Exception as e:
        log.error(f"更新超時設定時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新設定時發生伺服器內部錯誤。")
