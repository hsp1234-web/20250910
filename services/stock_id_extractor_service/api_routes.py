import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

# --- 本地模組匯入 (使用絕對路徑) ---
from services.stock_id_extractor_service.extractor import extract_stock_ids

# --- 日誌設定 ---
log = logging.getLogger(__name__)

# --- API Router 初始化 ---
router = APIRouter()

# --- Pydantic 模型定義 ---
# 定義 API 請求的資料結構
class TextProcessRequest(BaseModel):
    text: str

# --- API 端點定義 ---
@router.post("/api/extract_stock_ids", response_model=List[str])
async def extract_stock_ids_endpoint(request: TextProcessRequest) -> List[str]:
    """
    接收一段純文字，並從中提取所有有效的台股股票代號。
    """
    log.info(f"接收到新的股票代號提取請求，文字長度: {len(request.text)} 字元。")

    # 呼叫我們的核心提取邏輯
    valid_ids = extract_stock_ids(request.text)

    log.info(f"請求處理完成，共找到 {len(valid_ids)} 個有效代號。")
    return valid_ids

@router.get("/health", status_code=200)
async def health_check():
    """服務健康狀態檢查端點。"""
    return {"status": "ok", "service": "Stock ID Extractor Service"}