# src/api/routes/primary_dealer_keys.py
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import httpx

# 從相依性管理模組中匯入 get_service_url 函式
from ..dependencies import get_service_url

# --- 設定 ---
logger = logging.getLogger(__name__)
router = APIRouter()

# --- Pydantic 模型 ---
class KeyPayload(BaseModel):
    """ 用於接收 FRED API 金鑰的請求模型 """
    api_key: str = Field(..., description="要儲存的 FRED API 金鑰。")

# --- API 端點 ---

@router.post("/fred", summary="儲存 FRED API 金鑰")
async def save_fred_key(
    payload: KeyPayload,
    key_service_url: str = Depends(get_service_url("key_service"))
):
    """
    將使用者提供的 FRED API 金鑰安全地儲存到 key_service 微服務中。
    """
    if not payload.api_key:
        raise HTTPException(status_code=400, detail="API 金鑰不可為空。")

    async with httpx.AsyncClient() as client:
        try:
            # 呼叫 key_service 來儲存金鑰
            response = await client.post(
                f"{key_service_url}/keys/generic",
                json={"key_name": "FRED_API_KEY", "key_value": payload.api_key}
            )
            response.raise_for_status()  # 如果回應狀態碼不是 2xx，則會拋出例外
            return response.json()
        except httpx.RequestError as e:
            logger.error(f"無法連接到 key_service：{e}")
            raise HTTPException(status_code=503, detail="金鑰服務目前無法使用，請稍後再試。")
        except httpx.HTTPStatusError as e:
            logger.error(f"key_service 回應錯誤：{e.response.status_code} - {e.response.text}")
            detail = e.response.json().get("detail", "儲存金鑰時發生未知錯誤。")
            raise HTTPException(status_code=e.response.status_code, detail=detail)

@router.get("/fred", summary="獲取 FRED API 金鑰的狀態")
async def get_fred_key_status(
    key_service_url: str = Depends(get_service_url("key_service"))
):
    """
    從 key_service 檢查 FRED API 金鑰是否存在及其有效性。
    為了安全，此端點不會回傳完整的金鑰。
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{key_service_url}/keys/generic/FRED_API_KEY")

            # 如果金鑰不存在，key_service 會回傳 404
            if response.status_code == 404:
                return {"is_set": False, "is_valid": False, "detail": "尚未設定 FRED API 金鑰。"}

            response.raise_for_status()
            # 如果金鑰存在，我們假設它是有效的（因為 bond_service 會在啟動時驗證）
            # 我們只回傳一個狀態，表示金鑰已經設定
            return {"is_set": True, "is_valid": True, "detail": "FRED API 金鑰已設定。"}

        except httpx.RequestError as e:
            logger.error(f"無法連接到 key_service：{e}")
            return {"is_set": False, "is_valid": False, "detail": "無法連接到金鑰服務。"}
        except httpx.HTTPStatusError as e:
            logger.error(f"key_service 回應錯誤：{e.response.status_code} - {e.response.text}")
            return {"is_set": False, "is_valid": False, "detail": "檢查金鑰狀態時發生錯誤。"}