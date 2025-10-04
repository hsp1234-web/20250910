# services/key_master_service/models.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class KeyBase(BaseModel):
    """
    金鑰資料的基礎模型，定義通用欄位。
    """
    key_name: str = Field(..., description="用於識別金鑰的名稱，例如 'FRED_API_KEY_1'")
    key_type: str = Field(..., description="金鑰的類型，例如 'FRED' 或 'GEMINI'")

class KeyCreate(KeyBase):
    """
    用於新增或更新金鑰的請求模型。
    """
    key_value: str = Field(..., description="API 金鑰的實際值")

class KeyInfo(KeyBase):
    """
    用於回傳金鑰資訊的回應模型（不包含金鑰值以策安全）。
    """
    key_hash: str = Field(..., description="金鑰值的 SHA256 雜湊值（前16碼）")
    is_valid: bool = Field(..., description="金鑰當前是否有效")
    last_validated_at: Optional[datetime] = Field(None, description="上次驗證時間")

    class Config:
        orm_mode = True # FastAPI 舊版寫法，新版為 from_attributes=True
        from_attributes = True

class UpsertResponse(BaseModel):
    """
    新增或更新操作的回應模型。
    """
    message: str
    key_hash: str

class ValidKeyResponse(BaseModel):
    """
    回傳可用金鑰的回應模型。
    """
    key_value: str