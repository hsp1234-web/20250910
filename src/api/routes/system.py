# src/api/routes/system.py

import json
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Response

router = APIRouter()

SERVICE_REGISTRY_FILE = Path("/tmp/service_registry.json")

@router.get("/api/service_registry", tags=["System"])
async def get_service_registry():
    """
    讀取並回傳微服務的註冊資訊 (例如：它們運行的埠號)。
    前端可以透過此端點來動態發現後端服務的位址。
    """
    if not SERVICE_REGISTRY_FILE.exists():
        raise HTTPException(status_code=404, detail="服務註冊檔案不存在，後端服務可能尚未完全啟動。")

    try:
        with open(SERVICE_REGISTRY_FILE, 'r', encoding='utf-8') as f:
            registry_data = json.load(f)
        return registry_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取服務註冊檔案時發生錯誤: {e}")

@router.get("/api/key_status/fred", tags=["System"])
async def get_fred_key_status():
    """
    檢查 FRED_API_KEY 是否已在環境變數中設定。
    這是一個最小化的端點，讓前端能感知後端金鑰狀態，而不需更動核心金鑰管理系統。
    """
    api_key = os.environ.get('FRED_API_KEY')
    return {"available": bool(api_key)}
