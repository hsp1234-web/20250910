import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks, Response
from pydantic import BaseModel, HttpUrl

# --- 本地模組匯入 (使用相對路徑) ---
# 匯入我們在 repository 和 processor 中建立的函式
from .repository import create_processing_task
from .processor import process_document_url

# --- 日誌設定 ---
log = logging.getLogger(__name__)

# --- API Router 初始化 ---
router = APIRouter()

# --- Pydantic 模型定義 ---
# 定義 API 請求的資料結構
class DocumentProcessRequest(BaseModel):
    url: HttpUrl # 使用 HttpUrl 型別可以自動驗證傳入的是一個合法的 URL

# --- API 端點定義 ---
@router.post("/api/process_document", status_code=202)
async def process_document_endpoint(
    request: DocumentProcessRequest,
    background_tasks: BackgroundTasks,
    response: Response
):
    """
    接收一個文件 URL，並將其加入到背景處理佇列中。

    這個端點會立即回傳，而實際的處理（下載、分析等）將在背景執行。
    """
    source_url = str(request.url)
    log.info(f"接收到新的文件處理請求，URL: {source_url}")

    # 步驟 1: 在資料庫中建立一個處理任務
    # create_processing_task 會檢查 URL 是否已存在，如果已存在則回傳 False
    is_new_task = await asyncio.to_thread(create_processing_task, source_url)

    if is_new_task:
        # 步驟 2: 如果是新任務，則將其加入到 FastAPI 的背景任務中
        log.info(f"URL '{source_url}' 是一個新任務，將其加入背景處理佇列。")
        background_tasks.add_task(process_document_url, source_url)
        return {"message": "文件已成功加入處理佇列。", "url": source_url}
    else:
        # 如果任務已存在，我們回傳一個參考性的訊息，避免重複處理
        log.warning(f"URL '{source_url}' 的任務已存在，將不重複處理。")
        # 修正：明確地將狀態碼設為 200 OK
        response.status_code = 200
        return {"message": "文件處理任務已存在，無需重複加入。", "url": source_url}

@router.get("/health", status_code=200)
async def health_check():
    """服務健康狀態檢查端點。"""
    return {"status": "ok", "service": "Document Processor Service"}
import asyncio