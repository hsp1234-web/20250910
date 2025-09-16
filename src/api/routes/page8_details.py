# --- 檔案: src/api/routes/page8_details.py ---
# --- 說明: 提供檔案總覽頁面所需的後端 API ---

import logging
import sys
import json
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel

# --- 路徑修正與模듈匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 核心模組匯入 ---
# V4 優化：移除 get_client，改為依賴注入
# from db.client import get_client
from db.client import DBClient
from ..api_server import get_db
from fastapi import Depends

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()
# V4 優化：移除在模組加載時建立的客戶端實例。
# DB_CLIENT = get_client()
# 為了安全性，定義允許存取的目錄
ALLOWED_DIRS = [
    str(SRC_DIR.parent / "temp_json"),
    str(SRC_DIR.parent / "reports")
]

# --- API 端點 ---

@router.get("/details/{file_hash}")
async def get_file_details_by_hash(file_hash: str, db: DBClient = Depends(get_db)):
    """
    (V4 優化後) 根據檔案雜湊值，獲取檔案的完整生命週期資訊。
    """
    log.info(f"正在查詢 file_hash 為 {file_hash} 的詳細資訊...")

    # V4 優化：使用透過 Depends 注入的共享 db 實例
    all_occurrences = db.get_urls_by_hash(file_hash)

    if not all_occurrences:
        raise HTTPException(status_code=404, detail=f"找不到雜湊值為 {file_hash} 的檔案紀錄。")

    primary_record = all_occurrences[0]
    file_id = primary_record.get("id")

    analysis_task = None
    if file_id:
        analysis_task = db.get_analysis_task_by_file_id(file_id)

    response_data = {
        "file_hash": file_hash,
        "primary_record": primary_record,
        "all_occurrences": all_occurrences,
        "analysis_task": analysis_task
    }

    return response_data

@router.get("/get_json_content")
async def get_json_content(path: str = Query(..., description="要讀取的 JSON 檔案路徑")):
    """
    安全地讀取並回傳指定路徑的 JSON 檔案內容。
    """
    log.info(f"請求讀取 JSON 檔案: {path}")

    try:
        target_path = Path(path).resolve()

        # 安全性檢查：確保請求的路徑在允許的目錄範圍內
        is_safe = False
        for allowed_dir in ALLOWED_DIRS:
            # 使用 Path.is_relative_to() 進行更可靠的路徑檢查
            if target_path.is_relative_to(Path(allowed_dir).resolve()):
                is_safe = True
                break

        if not is_safe:
            log.warning(f"偵測到不安全的檔案路徑請求: {path}")
            raise HTTPException(status_code=403, detail="禁止存取指定的檔案路徑。")

        if not target_path.exists() or not target_path.is_file():
            raise HTTPException(status_code=404, detail="找不到指定的 JSON 檔案。")

        with open(target_path, "r", encoding="utf-8") as f:
            content = json.load(f)

        return content

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="無法解析 JSON 檔案。")
    except Exception as e:
        log.error(f"讀取 JSON 檔案 {path} 時發生錯誤: {e}", exc_info=True)
        # 避免洩漏詳細的伺服器錯誤
        raise HTTPException(status_code=500, detail="讀取檔案時發生內部錯誤。")
