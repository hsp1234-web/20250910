# services/essay_ingestion_service/main.py
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import logging
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional

# --- 核心邏輯模組匯入 ---

# JULES: 舊有的聊天紀錄解析邏輯
# 使用相對匯入以符合套件標準
from .logic import parse_chat_log, save_parsed_data_to_db

# JULES: 新增的文件分析邏輯
# 使用相對匯入
from .document_analyzer import process_document_url
from .document_repository import initialize_database as initialize_document_db


# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('essay_ingestion_service_main')

# --- 應用程式生命週期事件 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """在應用程式啟動時執行的生命週期事件。"""
    log.info("「小作文擷取服務」啟動中...")
    # JULES: 初始化新的文件分析資料庫
    log.info("正在初始化文件分析資料庫...")
    initialize_document_db()
    log.info("✅ 服務已就緒，可以開始接收請求。")
    yield
    log.info("「小作文擷取服務」正在關閉。")

# --- FastAPI 應用實例 ---
app = FastAPI(
    title="小作文擷取服務 (Essay Ingestion Service)",
    description="一個多功能微服務，用於：1. 解析 LINE 聊天紀錄、2. 接收文件 URL 並進行圖文分析。",
    version="2.0.0", # JULES: 版本升級，反映重大功能新增
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

# JULES: 新增的模型 for /analyze-document (文件分析)
class AnalyzeDocumentRequest(BaseModel):
    source_url: str

class AnalyzeDocumentResponse(BaseModel):
    message: str
    task_url: str


# --- API 端點 ---

# 端點 1: /ingest (現有功能)
@app.post("/ingest", response_model=IngestResponse, tags=["聊天紀錄解析"])
async def ingest_text(request: IngestRequest):
    """
    接收文字，解析後存入資料庫，並回傳新增的項目列表。
    """
    log.info("接收到 /ingest 請求。")
    if not request.text or not request.text.strip():
        log.warning("請求的文字內容為空。")
        raise HTTPException(status_code=400, detail="文字內容不可為空。")

    try:
        log.info("開始解析文字...")
        parsed_data = parse_chat_log(request.text)
        if not parsed_data:
            log.info("從文字中未解析出任何有效資料。")
            return IngestResponse(message="未解析出有效資料。", inserted_count=0, inserted_items=[])

        log.info(f"解析出 {len(parsed_data)} 筆資料，準備存入資料庫...")
        inserted_items = save_parsed_data_to_db(parsed_data, source_text=request.text)
        inserted_count = len(inserted_items)

        return IngestResponse(
            message=f"處理完成，成功新增 {inserted_count} 筆資料。",
            inserted_count=inserted_count,
            inserted_items=inserted_items
        )

    except Exception as e:
        log.error(f"處理 /ingest 請求時發生未預期的錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"內部伺服器錯誤: {e}")

# JULES: 端點 2: /analyze-document (新功能)
@app.post("/analyze-document", response_model=AnalyzeDocumentResponse, tags=["文件圖文分析"])
async def analyze_document(request: AnalyzeDocumentRequest, background_tasks: BackgroundTasks):
    """
    接收文件 URL，並在背景啟動一個完整的「下載 -> 拆解 -> 分析 -> 保存」工作流程。
    """
    log.info(f"接收到 /analyze-document 請求，URL: {request.source_url}")
    if not request.source_url or not request.source_url.strip():
        log.warning("請求的 source_url 為空。")
        raise HTTPException(status_code=400, detail="source_url 不可為空。")

    # 將耗時的處理任務交由背景執行，API 立即回傳
    background_tasks.add_task(process_document_url, request.source_url)

    log.info(f"已將 URL '{request.source_url}' 的分析任務加入背景佇列。")

    return AnalyzeDocumentResponse(
        message="文件分析任務已成功排程，正在背景處理中。",
        task_url=request.source_url
    )


# --- 啟動配置 ---
if __name__ == "__main__":
    log.info("準備以獨立模式啟動「小作文擷取服務」...")
    # JULES: 端口號建議更改以避免與其他服務衝突，但暫時維持 8001
    uvicorn.run(app, host="0.0.0.0", port=8001)