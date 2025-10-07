import logging
from pathlib import Path
import sys
import json
import httpx
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from db.client import DBClient
from ..dependencies import get_db

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()
SERVICE_REGISTRY_FILE = Path("/tmp/service_registry.json")

# --- Pydantic 模型 ---
class ProcessRequest(BaseModel):
    ids: List[int]

# --- 輔助函式：動態服務發現 ---
def get_service_url(service_name: str) -> str:
    """從服務註冊檔案中動態讀取指定服務的基礎 URL。"""
    if not SERVICE_REGISTRY_FILE.exists():
        raise FileNotFoundError(f"服務註冊檔案不存在: {SERVICE_REGISTRY_FILE}")
    with open(SERVICE_REGISTRY_FILE, 'r') as f:
        registry = json.load(f)
    service_info = registry.get(service_name)
    if not service_info or not service_info.get("port"):
        raise ValueError(f"在服務註冊檔案中找不到 '{service_name}' 的有效設定。")
    return f"http://127.0.0.1:{service_info['port']}"

# --- API 端點 ---

@router.post("/start_processing", summary="啟動小作文 AI 分析")
async def start_essay_processing(payload: ProcessRequest):
    """
    接收檔案 ID 列表，並將請求代理到 document_processor_service 進行處理。
    這是一個簡化後的、更穩健的實現，它重用了現有的服務能力。
    """
    log.info(f"API (essay_performance): 收到對 {len(payload.ids)} 個項目的代理請求。")
    if not payload.ids:
        raise HTTPException(status_code=400, detail="未提供要處理的檔案 ID。")
    try:
        # 1. 動態發現 document_processor_service 的位址
        processor_service_url = get_service_url("document_processor_service")
        target_url = f"{processor_service_url}/api/processor/start_processing"

        # 2. 建立 HTTP 客戶端並轉發請求
        async with httpx.AsyncClient(timeout=60.0) as client:
            log.info(f"正在將請求轉發至: {target_url}")
            response = await client.post(target_url, json={"ids": payload.ids})

            # 3. 檢查回應並將其直接回傳給前端
            response.raise_for_status()
            log.info("請求已成功轉發至 document_processor_service。")
            return JSONResponse(content=response.json(), status_code=response.status_code)

    except (FileNotFoundError, ValueError) as e:
        log.error(f"服務發現失敗: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"服務發現失敗: {e}")
    except httpx.RequestError as e:
        log.error(f"請求 document_processor_service 時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="與後端處理服務的通訊失敗。")
    except httpx.HTTPStatusError as e:
        # 將下游服務的錯誤直接透傳給客戶端
        log.error(f"下游服務回傳錯誤: {e.response.status_code} {e.response.text}")
        return JSONResponse(content=e.response.json(), status_code=e.response.status_code)


@router.get("/get_files", summary="獲取可用於分析的檔案列表")
async def get_files_for_performance_analysis(db: DBClient = Depends(get_db)):
    """獲取所有狀態為 'completed' (已下載完成) 的檔案列表。"""
    log.info("API (essay_performance): 收到獲取已下載檔案列表的請求。")
    try:
        rows = db.get_urls_by_statuses(statuses=['completed'])
        results = [
            {
                "id": row['id'], "url": row['url'],
                "filename": Path(row['local_path']).name if row.get('local_path') else 'N/A',
                "title": row.get('title'), "author": row.get('author'),
                "message_date": row.get('message_date')
            } for row in rows
        ]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API (essay_performance): 獲取已下載檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取已下載檔案時發生伺服器內部錯誤。")

@router.get("/get_reports", summary="獲取所有已完成的 AI 分析報告")
async def get_all_completed_reports(db: DBClient = Depends(get_db)):
    """獲取所有 stage1_status 為 'completed' 的分析任務，用於報告頁面生成。"""
    log.info("API (essay_performance): 收到獲取所有已完成報告的請求。")
    try:
        all_tasks = db.get_all_analysis_tasks()
        completed_reports = []
        for task in all_tasks:
            if task.get('stage1_status') == 'completed' and task.get('stage1_result_json'):
                try:
                    analysis_result = json.loads(task['stage1_result_json'])
                    report_item = {
                        "task_id": task['id'], "file_id": task['source_document_id'],
                        "filename": task['filename'], "analysis": analysis_result
                    }
                    completed_reports.append(report_item)
                except (json.JSONDecodeError, TypeError):
                    log.warning(f"無法解析任務 ID {task.get('id')} 的分析結果 JSON。")
                    continue
        return JSONResponse(content=completed_reports)
    except Exception as e:
        log.error(f"API (essay_performance): 獲取已完成報告時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取已完成報告時發生伺服器內部錯誤。")