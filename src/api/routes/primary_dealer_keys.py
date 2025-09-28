# src/api/routes/primary_dealer_keys.py
import logging
import json
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import httpx

# --- 設定 ---
logger = logging.getLogger(__name__)
router = APIRouter()

# --- Pydantic 模型 ---
class KeyPayload(BaseModel):
    """ 用於接收 FRED API 金鑰的請求模型 """
    api_key: str = Field(..., description="要儲存的 FRED API 金鑰。")

# --- 輔助函式與依賴 ---
def _get_key_service_url():
    """
    從服務註冊檔案中同步讀取 key_service 的 URL。
    這是一個依賴項，將在路由函式中被呼叫。
    """
    try:
        # 注意：在 FastAPI 的依賴注入中，我們應該使用同步 I/O
        with open("/tmp/service_registry.json", "r") as f:
            registry = json.load(f)

        key_service_info = registry.get("key_service")
        if key_service_info and "port" in key_service_info:
            url = f"http://127.0.0.1:{key_service_info['port']}"
            return url
        else:
            logger.error("在服務註冊中心找不到 key_service 或其埠號。")
            raise HTTPException(status_code=503, detail="金鑰服務目前無法使用 (註冊資訊不完整)。")

    except FileNotFoundError:
        logger.error("找不到服務註冊檔案 /tmp/service_registry.json。")
        raise HTTPException(status_code=503, detail="金鑰服務目前無法使用 (註冊檔案遺失)。")
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"讀取或解析服務註冊檔案時發生錯誤: {e}")
        raise HTTPException(status_code=500, detail="讀取服務設定時發生內部錯誤。")

# --- API 端點 ---

@router.post("/fred", summary="儲存 FRED API 金鑰")
async def save_fred_key(
    payload: KeyPayload,
    key_service_url: str = Depends(_get_key_service_url)
):
    """
    將使用者提供的 FRED API 金鑰安全地儲存到 key_service 微服務中。
    """
    if not payload.api_key:
        raise HTTPException(status_code=400, detail="API 金鑰不可為空。")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            # 修正1: 呼叫 key_service 正確的端點 /api/keys
            # 修正2: 傳送 key_service 預期的 JSON 結構 {"api_key": ..., "name": ...}
            response = await client.post(
                f"{key_service_url}/api/keys",
                json={"api_key": payload.api_key, "name": "FRED_API_KEY"}
            )

            # 如果金鑰已存在 (409 Conflict)，我們視為一個可接受的「成功」場景
            if response.status_code == 409:
                return {"message": "金鑰已存在，無需更新。"}

            response.raise_for_status()
            return response.json()

        except httpx.RequestError as e:
            logger.error(f"無法連接到 key_service：{e}")
            raise HTTPException(status_code=503, detail="金鑰服務目前無法使用，請稍後再試。")
        except httpx.HTTPStatusError as e:
            logger.error(f"key_service 回應錯誤：{e.response.status_code} - {e.response.text}")
            detail_json = e.response.json()
            detail_msg = detail_json.get("detail", "儲存金鑰時發生未知錯誤。")
            raise HTTPException(status_code=e.response.status_code, detail=detail_msg)

@router.get("/fred", summary="獲取 FRED API 金鑰的狀態")
async def get_fred_key_status(
    key_service_url: str = Depends(_get_key_service_url)
):
    """
    從 key_service 檢查 FRED API 金鑰是否存在及其有效性。
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 修正: 呼叫我們在 key_service 中新增的按名稱查詢端點
            response = await client.get(f"{key_service_url}/api/keys/FRED_API_KEY")

            if response.status_code == 200:
                key_data = response.json()
                return {
                    "is_set": True,
                    "is_valid": key_data.get("is_valid", False),
                    "detail": "FRED API 金鑰已設定。"
                }
            elif response.status_code == 404:
                return {"is_set": False, "is_valid": False, "detail": "尚未設定 FRED API 金鑰。"}
            else:
                response.raise_for_status()

        except httpx.RequestError as e:
            logger.error(f"無法連接到 key_service：{e}")
            raise HTTPException(status_code=503, detail="無法連接到金鑰服務。")
        except httpx.HTTPStatusError as e:
            logger.error(f"key_service 回應錯誤：{e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=500, detail="檢查金鑰狀態時發生錯誤。")