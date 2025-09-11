# src/api/routes/page4_analyzer.py
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
# 檢查 sys.path 中是否已存在，如果不存在才加入
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from db.database import get_db_connection
from db.analysis_manager import create_analysis_task, get_all_analysis_tasks
# 註：key_manager 和背景任務的完整實作將在後續步驟中完成
# from core import key_manager

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()

# --- Pydantic 模型 ---
class NewAnalysisRequest(BaseModel):
    """新的分析請求模型，只要求來源檔案的 ID。"""
    file_id: int

# --- 背景任務 (暫存) ---
def run_full_trading_analysis(task_id: int):
    """
    這是新的、完整的交易分析背景任務的進入點。
    詳細的實作將在計畫的第二步驟中完成。
    """
    log.info(f"背景任務：已為分析任務 ID {task_id} 觸發。完整分析流程待實作...")
    # 在此處，我們將來會加入呼叫 Stage 1 AI、yfinance、回測、Stage 2 AI 的邏輯。
    pass

# --- API 端點 ---

@router.get("/processed_files", response_model=List[Dict[str, Any]])
async def get_processed_files():
    """獲取所有狀態為 'processed' 的檔案列表，用於前端下拉選單。"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, local_path FROM extracted_urls WHERE status = 'processed' ORDER BY created_at DESC")
        rows = cursor.fetchall()
        # 確保 local_path 不是 None 或空字串
        results = [{"id": row['id'], "filename": Path(row['local_path']).name} for row in rows if row['local_path']]
        return results
    except Exception as e:
        log.error(f"API: 獲取已處理檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取已處理檔案時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()

@router.post("/start_analysis")
async def start_new_analysis(payload: NewAnalysisRequest, background_tasks: BackgroundTasks):
    """
    啟動一個新的、基於藍圖的交易分析任務。
    """
    log.info(f"API: 收到新的交易分析請求，來源檔案 ID: {payload.file_id}")

    # 步驟 1: 在資料庫中建立一個新的分析任務紀錄
    new_task_id = create_analysis_task(source_document_id=payload.file_id)

    if not new_task_id:
        log.error(f"API: 無法為檔案 ID {payload.file_id} 在資料庫中建立分析任務。")
        raise HTTPException(status_code=500, detail="在資料庫中建立分析任務失敗。")

    log.info(f"API: 已成功建立分析任務，ID: {new_task_id}。準備加入背景處理佇列。")

    # 步驟 2: 將新任務加入背景處理
    background_tasks.add_task(run_full_trading_analysis, new_task_id)

    return JSONResponse(
        content={"message": f"已成功為檔案 ID {payload.file_id} 建立交易分析任務 (任務 ID: {new_task_id})。"},
        status_code=202  # 202 Accepted: 請求已被接受處理，但尚未完成
    )

@router.get("/analysis_tasks", response_model=List[Dict[str, Any]])
async def get_tasks():
    """獲取所有分析任務的歷史紀錄。"""
    try:
        tasks = get_all_analysis_tasks()
        return tasks
    except Exception as e:
        log.error(f"API: 獲取分析任務列表時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取分析任務列表時發生伺服器內部錯誤。")
