# services/line_parser_service/main.py
import uvicorn
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
import logging
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
import asyncio

# --- 核心邏輯模組匯入 ---
from .logic import parse_chat_log, save_parsed_data_to_db
from .document_analyzer import process_local_document

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('line_parser_service_main')

# --- 應用程式生命週期事件 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    在應用程式啟動時執行的生命週期事件。
    [V2 改造]: 新增信號量與通知佇列，以支援背景工作流。
    """
    log.info("「LINE 解析服務」啟動中...")
    # 建立一個信號量，限制併發的背景處理任務數量為 5
    app.state.processing_semaphore = asyncio.Semaphore(5)
    # 建立一個非同步佇列，用於從背景任務向主應用程式發送通知
    app.state.notification_queue = asyncio.Queue()
    log.info("✅ 背景任務基礎設施 (信號量, 佇列) 初始化完成。")
    log.info("✅ 服務已就緒，可以開始接收請求。")
    yield
    log.info("「LINE 解析服務」正在關閉。")

# --- FastAPI 應用實例 ---
app = FastAPI(
    title="LINE 解析服務 (Line Parser Service)",
    description="一個多功能微服務，用於：1. 解析 LINE 聊天紀錄、2. 接收本地文件並進行圖文分析。",
    version="4.0.0", # 版本升級，反映架構重構
    lifespan=lifespan
)

# --- 資料模型 (Pydantic Models) ---

# 模型 for /ingest (聊天紀錄解析)
class IngestRequest(BaseModel):
    text: str

class InsertedItem(BaseModel):
    id: int
    url: str
    title: Optional[str] = None
    author: Optional[str] = None
    message_date: Optional[str] = None

class IngestResponse(BaseModel):
    message: str
    inserted_count: int
    inserted_items: List[InsertedItem]

# 簡化後的模型，此服務只關心檔案路徑
class ProcessLocalDocumentRequest(BaseModel):
    file_path: str

# --- API 端點 ---

# 端點 1: /ingest (現有功能)
@app.post("/ingest", response_model=IngestResponse, tags=["聊天紀錄解析"])
async def ingest_text(request: Request, payload: IngestRequest, background_tasks: BackgroundTasks):
    """
    [V2 改造]: 增加 BackgroundTasks 支援。
    接收文字，解析後存入資料庫，為每個新項目啟動一個背景處理工作流，並立即回傳。
    """
    log.info("接收到 /ingest 請求。")
    if not payload.text or not payload.text.strip():
        log.warning("請求的文字內容為空。")
        raise HTTPException(status_code=400, detail="文字內容不可為空。")

    try:
        log.info("開始解析文字...")
        parsed_data = parse_chat_log(payload.text)
        if not parsed_data:
            log.info("從文字中未解析出任何有效資料。")
            return IngestResponse(message="未解析出有效資料。", inserted_count=0, inserted_items=[])

        log.info(f"解析出 {len(parsed_data)} 筆資料，準備存入資料庫並啟動背景工作流...")

        # [V2 改造]: 將 request 和 background_tasks 傳遞下去
        inserted_items = save_parsed_data_to_db(
            parsed_data=parsed_data,
            source_text=payload.text,
            request=request,
            background_tasks=background_tasks
        )
        inserted_count = len(inserted_items)

        return IngestResponse(
            message=f"處理完成，已為 {inserted_count} 筆新資料啟動背景處理任務。",
            inserted_count=inserted_count,
            inserted_items=inserted_items
        )
    except Exception as e:
        log.error(f"處理 /ingest 請求時發生未預期的錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"內部伺服器錯誤: {e}")

# 重構後的端點，僅負責分析並直接回傳結果
@app.post("/process-local-document", response_model=Dict[str, Any], tags=["文件圖文分析"])
async def process_local_document_endpoint(request: ProcessLocalDocumentRequest):
    """
    接收一個本地檔案路徑，對該檔案進行分析，並直接回傳分析結果的字典。
    這是一個同步端點，會等待分析完成後才回傳結果。
    """
    log.info(f"接收到 /process-local-document 請求，路徑: {request.file_path}")

    try:
        # 直接呼叫處理本地檔案的函式，並等待其完成
        analysis_result = await process_local_document(file_path=request.file_path)
        # 直接回傳分析結果
        return analysis_result

    except FileNotFoundError as e:
        log.error(f"檔案未找到錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=404, detail=str(e))
    except ConnectionError as e:
        # (Jules): 捕捉由 document_analyzer 拋出的、關於下游服務不可用的特定錯誤。
        log.error(f"下游服務連線錯誤: {e}", exc_info=True)
        # 回傳 503 Service Unavailable，並附帶清晰的錯誤訊息。
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        # 捕捉所有其他未預期的異常，並回傳 500 錯誤
        log.error(f"處理本地文件時發生未預期錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析文件時發生內部伺服器錯誤: {e}")

# --- 啟動配置 ---
if __name__ == "__main__":
    log.info("準備以獨立模式啟動「小作文擷取服務」...")
    uvicorn.run(app, host="0.0.0.0", port=8001)
