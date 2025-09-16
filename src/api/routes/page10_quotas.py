# src/api/routes/page10_quotas.py
import logging
import sys
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from db import quota_manager

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()

# --- Pydantic 模型 ---
class Quota(BaseModel):
    model_name: str = Field(..., description="模型的唯一識別名稱")
    rpm: int = Field(..., gt=0, description="每分鐘請求數 (Requests Per Minute)")
    tpm: int = Field(..., gt=0, description="每分鐘 Token 數 (Tokens Per Minute)")
    rpd: int = Field(..., gt=0, description="每日請求數 (Requests Per Day)")

    class Config:
        orm_mode = True

class UpdateQuotaRequest(BaseModel):
    quotas: List[Quota]

# --- API 端點 ---

@router.get("", response_model=List[Quota], summary="獲取所有模型的流量限制設定")
async def get_quotas():
    """
    從資料庫中讀取並回傳所有已設定的模型流量限制。
    """
    try:
        quotas_data = quota_manager.get_all_quotas()
        return quotas_data
    except Exception as e:
        log.error(f"獲取流量限制設定時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法從資料庫讀取流量限制設定。")

@router.post("", summary="更新一或多個模型的流量限制設定")
async def update_quotas_endpoint(payload: UpdateQuotaRequest):
    """
    接收一個包含多個模型設定的列表，並將其更新或插入到資料庫中。
    採用 "UPSERT" (Update or Insert) 模式。
    """
    if not payload.quotas:
        raise HTTPException(status_code=400, detail="更新請求中的 `quotas` 列表不可為空。")

    try:
        # Pydantic 模型轉換為字典列表
        quotas_to_update = [q.dict() for q in payload.quotas]
        affected_rows = quota_manager.update_quotas(quotas_to_update)
        return {
            "message": "流量限制設定已成功更新。",
            "affected_rows": affected_rows
        }
    except Exception as e:
        log.error(f"更新流量限制設定時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新流量限制設定時發生伺服器內部錯誤。")
